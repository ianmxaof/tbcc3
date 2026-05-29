import { useEffect } from "react";
import { bindTbccDelegatedCopy } from "../utils/clipboardToast";

/** Mount once in App — enables data-tbcc-copy buttons everywhere in the dashboard. */
export function TbccClipboardInit() {
  useEffect(() => {
    bindTbccDelegatedCopy(document);
  }, []);
  return null;
}
