/* Only the public offline notice is cached. Never cache pages or API responses. */
const CACHE="daljam-offline-v1";
self.addEventListener("install",event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.add("/offline.html")));
  self.skipWaiting();
});
self.addEventListener("activate",event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith("daljam-offline-")&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener("fetch",event=>{
  if(event.request.mode!=="navigate"||event.request.method!=="GET"||new URL(event.request.url).origin!==self.location.origin)return;
  event.respondWith(fetch(event.request,{cache:"no-store"}).catch(async()=>{
    return await caches.match("/offline.html")||new Response("인터넷과 서버 PC 연결을 확인해 주세요.",{status:503,headers:{"Content-Type":"text/plain; charset=utf-8"}});
  }));
});
