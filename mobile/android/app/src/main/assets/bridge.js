(function(platform){
 if(window.DaljamNative)return;
 var pending=new Map(),seq=0;
 window.__daljamReply=function(reply){var task=pending.get(reply.id);if(!task)return;clearTimeout(task.timer);pending.delete(reply.id);reply.error?task.reject(new Error(reply.error)):task.resolve(reply.result);};
 if(platform==='android')window.DaljamBridge.onmessage=function(e){try{window.__daljamReply(JSON.parse(e.data));}catch(_){}};
 window.DaljamNative={platform:platform,request:function(method,payload){return new Promise(function(resolve,reject){
  var id=String(++seq),timer=setTimeout(function(){pending.delete(id);reject(new Error('연결 확인이 지연되고 있어요. 다시 시도해 주세요.'));},70000);
  pending.set(id,{resolve:resolve,reject:reject,timer:timer});var message={id:id,method:method,payload:payload||{}};
  if(platform==='android')window.DaljamBridge.postMessage(JSON.stringify(message));else window.webkit.messageHandlers.DaljamBridge.postMessage(message);
 });}};
 window.dispatchEvent(new Event('daljam-native-ready'));
})('android');