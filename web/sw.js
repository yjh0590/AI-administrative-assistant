self.addEventListener("install", event => event.waitUntil(self.skipWaiting()));
self.addEventListener("activate", event => event.waitUntil(clients.claim()));

self.addEventListener("push", event => {
  const data = event.data?.json() ?? {};
  event.waitUntil(self.registration.showNotification(data.title ?? "AI 비서", {
    body: data.body ?? "새 브리핑을 확인하세요.",
    icon: "/icon-192.png",
    tag: data.tag ?? "briefing",
    data: { route: data.route ?? (data.tag === "briefing-test" ? "/#settings" : "/#briefing") },
  }));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  event.waitUntil(clients.openWindow(event.notification.data?.route ?? "/#briefing"));
});
