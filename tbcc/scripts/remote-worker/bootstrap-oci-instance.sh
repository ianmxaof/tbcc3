#!/usr/bin/env bash
# Create TBCC remote-worker VM on Oracle Cloud (VCN + public subnet + Ubuntu 24.04 A1 Flex).
# Prereqs: oci CLI configured (`oci setup config`), SSH pubkey at ~/.ssh/oci_tbcc.pub
#
# Windows (opens Git Bash for you):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\scripts\remote-worker\bootstrap-oci-instance.ps1
#
# Git Bash / WSL directly:
#   export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True
#   export ROTATE_REGIONS=false
#   export OCI_CLI_REGION=us-sanjose-1
#   bash bootstrap-oci-instance.sh
#
# Optional env:
#   ROTATE_REGIONS=true|false          (default: true — only subscribed regions on tenancy)
#   OCI_REGIONS="us-phoenix-1 us-ashburn-1"   (override rotation list)
#   OCI_CLI_REGION=us-sanjose-1        (try this region first when rotating)
#   RETRY_DELAY_SECONDS=30             (pause between full rotation cycles)
#   MAX_ROUNDS=0                       (0 = keep trying until success)
#   COMPARTMENT_ID=ocid1.compartment...   (auto-detects tenancy root if unset)
#   SSH_PUBKEY_FILE=$HOME/.ssh/oci_tbcc.pub
#   INSTANCE_NAME=tbcc-scrape-worker
set -euo pipefail

export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING="${OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING:-True}"

INSTANCE_NAME="${INSTANCE_NAME:-tbcc-scrape-worker}"
VCN_NAME="${VCN_NAME:-tbcc-vcn}"
SUBNET_NAME="${SUBNET_NAME:-tbcc-public-subnet}"
VCN_CIDR="${VCN_CIDR:-10.0.0.0/16}"
SUBNET_CIDR="${SUBNET_CIDR:-10.0.0.0/24}"
SHAPE="${SHAPE:-VM.Standard.A1.Flex}"
OCPUS="${OCPUS:-1}"
MEMORY_GB="${MEMORY_GB:-6}"
SSH_PUBKEY_FILE="${SSH_PUBKEY_FILE:-$HOME/.ssh/oci_tbcc.pub}"
ROTATE_REGIONS="${ROTATE_REGIONS:-true}"
RETRY_DELAY_SECONDS="${RETRY_DELAY_SECONDS:-30}"
MAX_ROUNDS="${MAX_ROUNDS:-0}"

DEFAULT_REGIONS=(
  us-sanjose-1
  us-phoenix-1
  us-ashburn-1
  ca-montreal-1
  uk-london-1
  eu-frankfurt-1
  eu-amsterdam-1
  ap-tokyo-1
  ap-osaka-1
  ap-mumbai-1
  sa-saopaulo-1
)

if ! command -v oci >/dev/null 2>&1; then
  echo "Install OCI CLI first: https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm"
  exit 1
fi

if [[ ! -f "$SSH_PUBKEY_FILE" ]]; then
  echo "Missing SSH public key: $SSH_PUBKEY_FILE"
  echo "Generate: ssh-keygen -t ed25519 -f ~/.ssh/oci_tbcc -N \"\""
  exit 1
fi

resolve_compartment_id() {
  if [[ -n "${COMPARTMENT_ID:-}" && "$COMPARTMENT_ID" != "null" ]]; then
    return 0
  fi
  COMPARTMENT_ID="$(oci iam compartment list --compartment-id-in-subtree true --access-level ACCESSIBLE --all \
    --query "data[?\"lifecycle-state\"=='ACTIVE'] | [0].id" --raw-output 2>/dev/null || true)"
  if [[ -z "$COMPARTMENT_ID" || "$COMPARTMENT_ID" == "null" ]]; then
    local oci_config="${OCI_CLI_CONFIG_FILE:-$HOME/.oci/config}"
    if [[ -f "$oci_config" ]]; then
      COMPARTMENT_ID="$(grep -E '^tenancy=' "$oci_config" | head -1 | cut -d= -f2- | tr -d '\r')"
    fi
  fi
  if [[ -z "${COMPARTMENT_ID:-}" || "$COMPARTMENT_ID" == "null" ]]; then
    echo "Could not resolve COMPARTMENT_ID."
    echo "Set it to your tenancy OCID (root compartment), e.g.:"
    echo "  export COMPARTMENT_ID=\$(grep '^tenancy=' ~/.oci/config | cut -d= -f2-)"
    exit 1
  fi
}

build_region_list() {
  REGIONS=()
  local seen=""
  local region

  add_region() {
    local r="$1"
    [[ -z "$r" ]] && return 0
    case "$seen" in *"|$r|"*) return 0 ;; esac
    REGIONS+=("$r")
    seen="${seen}|$r|"
  }

  if [[ -n "${OCI_CLI_REGION:-}" ]]; then
    add_region "$OCI_CLI_REGION"
  fi
  if [[ -n "${OCI_REGIONS:-}" ]]; then
    for region in $OCI_REGIONS; do
      add_region "$region"
    done
  elif [[ "$ROTATE_REGIONS" == "true" ]]; then
    local subs
    subs="$(list_subscribed_regions)"
    if [[ -n "$subs" ]]; then
      for region in $subs; do
        add_region "$region"
      done
      echo "==> Subscribed regions only: ${REGIONS[*]}"
    else
      for region in "${DEFAULT_REGIONS[@]}"; do
        add_region "$region"
      done
    fi
  elif [[ -n "${OCI_CLI_REGION:-}" ]]; then
    : # already added
  else
    add_region "us-sanjose-1"
  fi

  if [[ ${#REGIONS[@]} -eq 0 ]]; then
    echo "No regions to try. Set OCI_REGIONS or OCI_CLI_REGION."
    exit 1
  fi
}

oci_err_is_capacity() {
  local err="$1"
  echo "$err" | grep -qi "Out of host capacity"
}

oci_err_is_not_authenticated() {
  local err="$1"
  echo "$err" | grep -qiE "NotAuthenticated|was not provided or was incorrect"
}

oci_capture() {
  # Usage: out="$(oci_capture oci ...)"  rc=$?
  local err_file rc out
  err_file="$(mktemp)"
  set +e
  out="$("$@" 2>"$err_file")"
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    cat "$err_file" >&2
    rm -f "$err_file"
    return "$rc"
  fi
  rm -f "$err_file"
  printf '%s' "$out"
  return 0
}

list_subscribed_regions() {
  local subs=""
  subs="$(oci iam region-subscription list --tenancy-id "$COMPARTMENT_ID" --all \
    --query "data[?\"status\"=='READY'].\"region-name\"" --raw-output 2>/dev/null || true)"
  if [[ -z "$subs" || "$subs" == "null" ]]; then
    subs="$(oci iam region-subscription list --tenancy-id "$COMPARTMENT_ID" --all \
      --query "data[].\"region-name\"" --raw-output 2>/dev/null || true)"
  fi
  if [[ -z "$subs" || "$subs" == "null" ]]; then
    local home="${OCI_CLI_REGION:-}"
    if [[ -z "$home" && -f "${OCI_CLI_CONFIG_FILE:-$HOME/.oci/config}" ]]; then
      home="$(grep -E '^region=' "${OCI_CLI_CONFIG_FILE:-$HOME/.oci/config}" | head -1 | cut -d= -f2- | tr -d '\r')"
    fi
    [[ -n "$home" ]] && subs="$home"
  fi
  echo "$subs"
}

resolve_ubuntu_image() {
  local region="$1"
  local image_id err_file
  err_file="$(mktemp)"

  image_id="$(oci compute image list --compartment-id "$COMPARTMENT_ID" \
    --operating-system "Canonical Ubuntu" \
    --operating-system-version "24.04" \
    --shape "$SHAPE" \
    --sort-by TIMECREATED --sort-order DESC --limit 1 \
    --query "data[0].id" --raw-output 2>"$err_file" || true)"
  if [[ -n "$image_id" && "$image_id" != "null" ]]; then
    rm -f "$err_file"
    echo "$image_id"
    return 0
  fi

  image_id="$(oci compute image list --compartment-id "$COMPARTMENT_ID" --all \
    --operating-system "Canonical Ubuntu" \
    --operating-system-version "24.04" \
    --sort-by TIMECREATED --sort-order DESC --limit 5 \
    --query "data[?\"lifecycle-state\"=='AVAILABLE'] | [0].id" --raw-output 2>/dev/null || true)"
  if [[ -n "$image_id" && "$image_id" != "null" ]]; then
    rm -f "$err_file"
    echo "$image_id"
    return 0
  fi

  if [[ -s "$err_file" ]]; then
    echo "==> Image lookup failed in $region:" >&2
    cat "$err_file" >&2
  fi
  rm -f "$err_file"
  return 1
}

provision_in_region() {
  local region="$1"
  export OCI_CLI_REGION="$region"
  local ad image_id vcn_id igw_id rt_id sl_id subnet_id existing instance_id
  local public_ip private_ip launch_err launch_rc

  echo ""
  echo "========================================"
  echo "==> Region: $region"
  echo "========================================"

  local ad_err_file ad_rc
  ad_err_file="$(mktemp)"
  set +e
  ad="$(oci iam availability-domain list --compartment-id "$COMPARTMENT_ID" \
    --query "data[0].name" --raw-output 2>"$ad_err_file")"
  ad_rc=$?
  set -e
  if [[ $ad_rc -ne 0 || -z "$ad" || "$ad" == "null" ]]; then
    local ad_err
    ad_err="$(cat "$ad_err_file")"
    rm -f "$ad_err_file"
    if oci_err_is_not_authenticated "$ad_err"; then
      echo "==> Skip: $region is not subscribed on this tenancy (401 NotAuthenticated)."
      echo "    Enable it in Oracle Console → Governance → Region management, or hunt capacity in a subscribed region only."
      return 2
    fi
    echo "$ad_err" >&2
    return 1
  fi
  rm -f "$ad_err_file"
  echo "==> Availability domain: $ad"

  if ! image_id="$(resolve_ubuntu_image "$region")"; then
    echo "==> Skip: could not resolve Ubuntu 24.04 image for $SHAPE in $region"
    return 2
  fi
  echo "==> Image: $image_id"

  vcn_id="$(oci network vcn list --compartment-id "$COMPARTMENT_ID" \
    --display-name "$VCN_NAME" --query "data[0].id" --raw-output 2>/dev/null || true)"
  if [[ -z "$vcn_id" || "$vcn_id" == "null" ]]; then
    echo "==> Creating VCN $VCN_NAME"
    vcn_id="$(oci network vcn create --compartment-id "$COMPARTMENT_ID" \
      --display-name "$VCN_NAME" --cidr-blocks "[\"$VCN_CIDR\"]" --dns-label tbccvcn \
      --query "data.id" --raw-output)"
  else
    echo "==> Reusing VCN $VCN_NAME ($vcn_id)"
  fi

  igw_id="$(oci network internet-gateway list --compartment-id "$COMPARTMENT_ID" --vcn-id "$vcn_id" \
    --query "data[0].id" --raw-output 2>/dev/null || true)"
  if [[ -z "$igw_id" || "$igw_id" == "null" ]]; then
    echo "==> Creating internet gateway"
    igw_id="$(oci network internet-gateway create --compartment-id "$COMPARTMENT_ID" \
      --vcn-id "$vcn_id" --display-name tbcc-igw --is-enabled true \
      --query "data.id" --raw-output)"
  fi

  rt_id="$(oci network route-table list --compartment-id "$COMPARTMENT_ID" --vcn-id "$vcn_id" \
    --display-name tbcc-public-rt --query "data[0].id" --raw-output 2>/dev/null || true)"
  if [[ -z "$rt_id" || "$rt_id" == "null" ]]; then
    echo "==> Creating route table"
    rt_id="$(oci network route-table create --compartment-id "$COMPARTMENT_ID" \
      --vcn-id "$vcn_id" --display-name tbcc-public-rt \
      --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$igw_id\"}]" \
      --query "data.id" --raw-output)"
  fi

  sl_id="$(oci network security-list list --compartment-id "$COMPARTMENT_ID" --vcn-id "$vcn_id" \
    --display-name tbcc-public-sl --query "data[0].id" --raw-output 2>/dev/null || true)"
  if [[ -z "$sl_id" || "$sl_id" == "null" ]]; then
    echo "==> Creating security list (SSH + outbound)"
    sl_id="$(oci network security-list create --compartment-id "$COMPARTMENT_ID" \
      --vcn-id "$vcn_id" --display-name tbcc-public-sl \
      --egress-security-rules '[{"destination":"0.0.0.0/0","protocol":"all","isStateless":false}]' \
      --ingress-security-rules '[{"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":22,"max":22}}}]' \
      --query "data.id" --raw-output)"
  fi

  subnet_id="$(oci network subnet list --compartment-id "$COMPARTMENT_ID" --vcn-id "$vcn_id" \
    --display-name "$SUBNET_NAME" --query "data[0].id" --raw-output 2>/dev/null || true)"
  if [[ -z "$subnet_id" || "$subnet_id" == "null" ]]; then
    echo "==> Creating public subnet $SUBNET_NAME"
    subnet_id="$(oci network subnet create --compartment-id "$COMPARTMENT_ID" \
      --vcn-id "$vcn_id" --display-name "$SUBNET_NAME" --cidr-block "$SUBNET_CIDR" \
      --route-table-id "$rt_id" --security-list-ids "[\"$sl_id\"]" \
      --prohibit-public-ip-on-vnic false \
      --query "data.id" --raw-output)"
  else
    echo "==> Reusing subnet $SUBNET_NAME ($subnet_id)"
  fi

  existing="$(oci compute instance list --compartment-id "$COMPARTMENT_ID" \
    --display-name "$INSTANCE_NAME" --lifecycle-state RUNNING \
    --query "data[0].id" --raw-output 2>/dev/null || true)"
  if [[ -n "$existing" && "$existing" != "null" ]]; then
    echo "==> Instance $INSTANCE_NAME already running: $existing"
    instance_id="$existing"
  else
    echo "==> Launching $INSTANCE_NAME ($SHAPE ${OCPUS} OCPU / ${MEMORY_GB} GB)"
    launch_err="$(mktemp)"
    set +e
    instance_id="$(oci compute instance launch \
      --compartment-id "$COMPARTMENT_ID" \
      --availability-domain "$ad" \
      --display-name "$INSTANCE_NAME" \
      --image-id "$image_id" \
      --shape "$SHAPE" \
      --shape-config "{\"ocpus\":$OCPUS,\"memoryInGBs\":$MEMORY_GB}" \
      --subnet-id "$subnet_id" \
      --assign-public-ip true \
      --ssh-authorized-keys-file "$SSH_PUBKEY_FILE" \
      --query "data.id" --raw-output 2>"$launch_err")"
    launch_rc=$?
    set -e
    if [[ $launch_rc -ne 0 ]]; then
      launch_err="$(cat "$launch_err")"
      rm -f "$launch_err"
      if oci_err_is_capacity "$launch_err"; then
        echo "==> Out of host capacity in $region"
        return 2
      fi
      echo "$launch_err" >&2
      return 1
    fi
    rm -f "$launch_err"
  fi

  echo "==> Waiting for instance to run..."
  oci compute instance wait --instance-id "$instance_id" --wait-for-state RUNNING >/dev/null

  public_ip="$(oci compute instance list-vnics --instance-id "$instance_id" \
    --query "data[0].\"public-ip\"" --raw-output)"
  private_ip="$(oci compute instance list-vnics --instance-id "$instance_id" \
    --query "data[0].\"private-ip\"" --raw-output)"

  echo ""
  echo "Done."
  echo "  Region:      $region"
  echo "  Instance ID: $instance_id"
  echo "  Public IP:   ${public_ip:-pending}"
  echo "  Private IP:  ${private_ip:-}"
  echo ""
  echo "SSH:"
  echo "  ssh -i ${SSH_PUBKEY_FILE%.pub} ubuntu@${public_ip}"
  echo ""
  echo "Save for remote worker setup:"
  echo "  export OCI_CLI_REGION=$region"
  return 0
}

resolve_compartment_id
build_region_list

echo "==> Compartment: $COMPARTMENT_ID"
if [[ "$ROTATE_REGIONS" == "true" ]]; then
  echo "==> Region rotation: ${REGIONS[*]}"
  echo "==> Retry delay between cycles: ${RETRY_DELAY_SECONDS}s (MAX_ROUNDS=${MAX_ROUNDS:-0} = unlimited)"
else
  echo "==> Single region: ${REGIONS[0]}"
  echo "==> Will retry every ${RETRY_DELAY_SECONDS}s until A1 capacity opens (leave window open)"
fi

round=1
set +e
while true; do
  if [[ "$MAX_ROUNDS" -gt 0 && "$round" -gt "$MAX_ROUNDS" ]]; then
    echo ""
    echo "Gave up after $MAX_ROUNDS rotation round(s). No A1 capacity found."
    echo "Try again later or set MAX_ROUNDS=0 to keep hunting."
    exit 1
  fi

  if [[ "$ROTATE_REGIONS" == "true" && ( "$MAX_ROUNDS" -eq 0 || "$round" -gt 1 ) ]]; then
    echo ""
    echo "---- Rotation round $round ----"
  elif [[ "$ROTATE_REGIONS" != "true" && "$round" -gt 1 ]]; then
    echo ""
    echo "---- Retry round $round ----"
  fi

  for region in "${REGIONS[@]}"; do
    provision_in_region "$region"
    rc=$?
    if [[ $rc -eq 0 ]]; then
      exit 0
    fi
    if [[ $rc -eq 1 ]]; then
      exit 1
    fi
  done

  round=$((round + 1))
  echo ""
  echo "==> No A1 capacity in subscribed region(s) this round. Sleeping ${RETRY_DELAY_SECONDS}s..."
  if [[ ${#REGIONS[@]} -eq 1 ]]; then
    echo "    (Only ${REGIONS[0]} is subscribed - free tier often has one region; keep retrying or try off-peak hours.)"
  fi
  sleep "$RETRY_DELAY_SECONDS"
done
