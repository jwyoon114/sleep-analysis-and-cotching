/* Only the public offline notice is cached. Never cache pages or API responses. */
const CACHE="daljam-offline-v2";
self.addEventListener("install",event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.add("/offline.html")));
  self.skipWaiting();
});
self.addEventListener("activate",event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith("daljam-offline-")&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener("fetch",event=>{
  const url=new URL(event.request.url);
  if(event.request.mode!=="navigate"||event.request.method!=="GET"||url.origin!==self.location.origin||url.pathname.startsWith("/downloads/"))return;
  event.respondWith(fetch(event.request,{cache:"no-store"}).catch(async()=>{
    return await caches.match("/offline.html")||new Response("인터넷 연결을 확인한 뒤 달잠을 다시 열어 주세요.",{status:503,headers:{"Content-Type":"text/plain; charset=utf-8"}});
  }));
});
