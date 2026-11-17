export function isAppleMobile(navigator: Pick<Navigator,"userAgent"|"platform"|"maxTouchPoints">) {
  return /iPhone|iPad|iPod/i.test(navigator.userAgent) || navigator.platform==="MacIntel"&&navigator.maxTouchPoints>1;
}

export function isStandalone() {
  return window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator&{standalone?: boolean}).standalone===true;
}

export type PushSupport = "native"|"apple-tab"|"unsupported"|"supported";

export function pushSupport(): PushSupport {
  if(window.DaljamNative || (/\bwv\b/i.test(navigator.userAgent)&&/Android/i.test(navigator.userAgent)))return "native";
  if(isAppleMobile(navigator)&&!isStandalone())return "apple-tab";
  if(!window.isSecureContext||!("serviceWorker" in navigator)||!("PushManager" in window)||!("Notification" in window))return "unsupported";
  return "supported";
}

export async function subscriptionId(subscription: PushSubscription) {
  const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(subscription.endpoint));
  return Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,"0")).join("");
}

export function applicationServerKey(value: string) {
  return Uint8Array.from(atob(value.replaceAll("-","+").replaceAll("_","/")),char=>char.charCodeAt(0));
}
