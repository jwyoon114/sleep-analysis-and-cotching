export type InstallPlatform = "native" | "ios" | "android" | "web";

export function installPlatform(
  {userAgent, platform, maxTouchPoints}: Pick<Navigator, "userAgent" | "platform" | "maxTouchPoints">,
  hasNativeBridge: boolean,
): InstallPlatform {
  if (hasNativeBridge) return "native";
  if (/iPhone|iPad|iPod/i.test(userAgent) || (platform === "MacIntel" && maxTouchPoints > 1)) return "ios";
  if (/Android/i.test(userAgent)) return "android";
  return "web";
}
