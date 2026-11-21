/* Only the public offline notice is cached. Never cache pages or API responses. */
const CACHE="daljam-offline-v3";
self.addEventListener("install",event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.add("/offline.html")));
  self.skipWaiting();
});
self.addEventListener("activate",event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith("daljam-offline-")&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener("fetch",event=>{
  const url=new URL(event.request.url);
  if(event.request.mode!=="navigate"||event.request.method!=="GET"||url.origin!==self.location.origin||
    url.pathname.startsWith("/downloads/")||url.pathname.startsWith("/api/"))return;
  event.respondWith(fetch(event.request,{cache:"no-store"}).catch(async()=>{
    return await caches.match("/offline.html")||new Response("인터넷 연결을 확인한 뒤 달잠을 다시 열어 주세요.",{status:503,headers:{"Content-Type":"text/plain; charset=utf-8"}});
  }));
});

const BEDTIME_TEST_TAG="daljam-bedtime-test";
const BEDTIME_REMINDER_TAG="daljam-bedtime-reminder";
self.addEventListener("push",event=>{
  let payload;
  try{payload=event.data?.json();}catch{return;}
  const isTest=payload?.kind==="bedtime-test";
  if(!isTest&&payload?.kind!=="bedtime-reminder")return;
  event.waitUntil(self.registration.showNotification(isTest?"달잠 테스트 알림":"달잠 취침 준비",{
    body:isTest?"달잠의 테스트 알림이에요. 누르면 계획 화면을 열어요.":"이제 잠들 준비를 해 볼까요? 누르면 계획 화면을 열어요.",
    icon:"/icons/app-192.png",
    tag:isTest?BEDTIME_TEST_TAG:BEDTIME_REMINDER_TAG,
  }));
});

self.addEventListener("notificationclick",event=>{
  if(![BEDTIME_TEST_TAG,BEDTIME_REMINDER_TAG].includes(event.notification.tag))return;
  event.notification.close();
  event.waitUntil((async()=>{
    const target=new URL("/?tab=plan",self.location.origin).href;
    for(const client of await self.clients.matchAll({type:"window",includeUncontrolled:true})){
      const url=new URL(client.url);
      if(url.origin!==self.location.origin||url.pathname!=="/")continue;
      try{
        const app=await client.navigate(target);
        if(app){await app.focus();return;}
      }catch{/* Try another window or start a new app window. */}
    }
    await self.clients.openWindow(target);
  })());
});
