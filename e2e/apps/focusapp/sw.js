self.addEventListener("fetch", e => { if (new URL(e.request.url).pathname === "/sw-probe") e.respondWith(new Response("from-focusapp-sw")); });
