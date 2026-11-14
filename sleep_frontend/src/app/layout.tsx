import type { Metadata, Viewport } from "next";
import PwaInstall from "@/components/pwa-install";
import "./globals.css";
import "./mobile-ui.css";

export const metadata: Metadata = {
  title: "달잠 · 나의 수면 리포트",
  description: "나의 밤을 이해하고, 더 편안한 내일을 준비하는 수면 기록과 AI 코칭",
  robots: { index: false, follow: false },
  appleWebApp: {capable:true,title:"달잠",statusBarStyle:"default"},
  icons: {apple:"/icons/apple-touch-icon.png",icon:"/icons/app-192.png"},
};
export const viewport:Viewport={width:"device-width",initialScale:1,viewportFit:"cover",themeColor:"#7861ac"};

export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="ko"><body>{children}<PwaInstall/></body></html>;
}
