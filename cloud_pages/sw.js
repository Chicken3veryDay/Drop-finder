const CACHE='dropfinder-cloud-v6';
const SHELL=['./','index.html','manifest.webmanifest','icon.svg','data/catalog.json','data/status.json'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  const url=new URL(event.request.url);
  if(url.origin!==location.origin)return;
  const dataRequest=url.pathname.includes('/data/')||url.pathname.startsWith('/api/');
  if(dataRequest){
    event.respondWith(caches.open(CACHE).then(async cache=>{
      const cached=await cache.match(event.request,{ignoreSearch:true});
      const refresh=fetch(event.request).then(response=>{if(response.ok)cache.put(event.request,response.clone());return response});
      if(cached){event.waitUntil(refresh.catch(()=>{}));return cached}
      return refresh;
    }).catch(()=>caches.match(event.request,{ignoreSearch:true})));
    return;
  }
  if(event.request.mode==='navigate'){
    event.respondWith(fetch(event.request).then(response=>{const copy=response.clone();caches.open(CACHE).then(cache=>cache.put('./',copy));return response}).catch(()=>caches.match('./')));
    return;
  }
  event.respondWith(caches.match(event.request,{ignoreSearch:true}).then(cached=>cached||fetch(event.request).then(response=>{if(response.ok)caches.open(CACHE).then(cache=>cache.put(event.request,response.clone()));return response})));
});
