import { Readable } from "node:stream";
import {
  S3Client,
  HeadObjectCommand,
  DeleteObjectCommand,
  GetObjectCommand,
  PutObjectCommand,
  type S3ClientConfig,
} from "@aws-sdk/client-s3";
import { Upload } from "@aws-sdk/lib-storage";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

/**
 * Backblaze B2 client (S3-compatible). All env reads are lazy so this module
 * can be imported in environments where the env isn't fully populated yet
 * (e.g. Next.js build).
 */

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Missing required env var: ${name}`);
  return v;
}

let cached: { client: S3Client; bucket: string } | null = null;

export function getB2(): { client: S3Client; bucket: string } {
  if (cached) return cached;
  const endpoint = requireEnv("B2_ENDPOINT");
  const region = process.env.B2_REGION || endpoint.match(/s3\.([^.]+)\./)?.[1] || "us-east-1";
  const bucket = requireEnv("B2_BUCKET");
  const config: S3ClientConfig = {
    endpoint,
    region,
    credentials: {
      accessKeyId: requireEnv("B2_KEY_ID"),
      secretAccessKey: requireEnv("B2_APP_KEY"),
    },
    forcePathStyle: false,
  };
  cached = { client: new S3Client(config), bucket };
  return cached;
}

export interface UploadOptions {
  key: string;
  body: Buffer | Uint8Array | Readable;
  contentType: string;
  contentLength?: number;
  metadata?: Record<string, string>;
}

/**
 * Streaming PUT. Uses @aws-sdk/lib-storage's multipart Upload so files of any
 * size work without buffering the whole thing in memory.
 */
export async function putStream(opts: UploadOptions): Promise<void> {
  const { client, bucket } = getB2();
  const upload = new Upload({
    client,
    params: {
      Bucket: bucket,
      Key: opts.key,
      Body: opts.body,
      ContentType: opts.contentType,
      ContentLength: opts.contentLength,
      Metadata: opts.metadata,
    },
    queueSize: 4,
    partSize: 1024 * 1024 * 16, // 16 MB parts
  });
  await upload.done();
}

export async function headObject(key: string): Promise<{
  exists: boolean;
  contentLength?: number;
  contentType?: string;
  etag?: string;
}> {
  const { client, bucket } = getB2();
  try {
    const r = await client.send(new HeadObjectCommand({ Bucket: bucket, Key: key }));
    return {
      exists: true,
      contentLength: r.ContentLength,
      contentType: r.ContentType,
      etag: r.ETag,
    };
  } catch (e: unknown) {
    const code =
      (e as { name?: string; $metadata?: { httpStatusCode?: number } }).$metadata?.httpStatusCode ??
      0;
    if (code === 404) return { exists: false };
    throw e;
  }
}

export async function deleteKey(key: string): Promise<void> {
  const { client, bucket } = getB2();
  await client.send(new DeleteObjectCommand({ Bucket: bucket, Key: key }));
}

/**
 * Signed GET URL. Useful for previewing private buckets in dev before the
 * Cloudflare CDN is in front of B2.
 */
export async function signedGetUrl(key: string, expiresInSec = 60 * 60): Promise<string> {
  const { client, bucket } = getB2();
  return getSignedUrl(client, new GetObjectCommand({ Bucket: bucket, Key: key }), {
    expiresIn: expiresInSec,
  });
}

/**
 * Presigned PUT for direct browser → B2 uploads (P4 bulk upload).
 */
export async function signedPutUrl(
  key: string,
  contentType: string,
  expiresInSec = 60 * 60
): Promise<string> {
  const { client, bucket } = getB2();
  return getSignedUrl(
    client,
    new PutObjectCommand({
      Bucket: bucket,
      Key: key,
      ContentType: contentType,
    }),
    { expiresIn: expiresInSec }
  );
}

export async function getObjectBuffer(key: string): Promise<{ body: Buffer; contentType: string }> {
  const { client, bucket } = getB2();
  const r = await client.send(new GetObjectCommand({ Bucket: bucket, Key: key }));
  const stream = r.Body;
  if (!stream) throw new Error(`empty body for ${key}`);
  const chunks: Uint8Array[] = [];
  for await (const chunk of stream as AsyncIterable<Uint8Array>) {
    chunks.push(chunk);
  }
  return {
    body: Buffer.concat(chunks),
    contentType: r.ContentType ?? "application/octet-stream",
  };
}

/**
 * Public delivery URL builder. In dev: signed B2 URL. In prod, when
 * NEXT_PUBLIC_MEDIA_BASE_URL is set to the Cloudflare CDN hostname, this
 * returns a stable, free-egress URL.
 */
export function publicMediaUrl(key: string): string {
  const base = process.env.NEXT_PUBLIC_MEDIA_BASE_URL;
  if (base) return `${base.replace(/\/$/, "")}/${key.replace(/^\//, "")}`;
  // No CDN configured - caller should fall back to signedGetUrl() for actual playback.
  // We still return a deterministic-but-non-working placeholder so the schema reads stay simple.
  const endpoint = process.env.B2_ENDPOINT?.replace(/\/$/, "") ?? "";
  const bucket = process.env.B2_BUCKET ?? "";
  if (!endpoint || !bucket) return key;
  return `${endpoint}/${bucket}/${key}`;
}

/**
 * Build a key with the project's conventional layout:
 *   media/YYYY/MM/<uuid>.<ext>
 */
export function buildMediaKey(uuid: string, ext: string, at: Date = new Date()): string {
  const yyyy = at.getUTCFullYear();
  const mm = String(at.getUTCMonth() + 1).padStart(2, "0");
  const cleanExt = ext.replace(/^\./, "").toLowerCase();
  return `media/${yyyy}/${mm}/${uuid}.${cleanExt}`;
}
