import type {MetadataRoute} from "next";

export default function manifest():MetadataRoute.Manifest {
  return {
    id:"/",name:"달잠 · 나의 수면 리포트",short_name:"달잠",lang:"ko",
    description:"수면 기록, 시간별 그래프와 AI 생활습관 코칭",
    start_url:"/",scope:"/",display:"standalone",
    background_color:"#0b1025",theme_color:"#0b1025",
    icons:[{src:"/icons/app-192.png",sizes:"192x192",type:"image/png"},
      {src:"/icons/app-512.png",sizes:"512x512",type:"image/png"},
      {src:"/icons/app-maskable.png",sizes:"512x512",type:"image/png",purpose:"maskable"}],
  };
}
