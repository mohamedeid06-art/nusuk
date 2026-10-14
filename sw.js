// =========================================================================
// Nusuk ERP Pro - Service Worker (sw.js)
// إدارة الكاش، استثناء السيرفر المحلي وسحابة Google، وتحديث فوري للملفات
// =========================================================================

const CACHE_NAME = "nusuk-erp-pro-v2";
const ASSETS_TO_CACHE = [
  "./",
  "./index.html",
  "./style.css",
  "./manifest.json",
  "./icon.svg",
  "./js/cloud-api.js",
  "./js/planner-accounting.js",
  "./js/automation.js"
];

// 1. التثبيت والتخزين المؤقت
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE).catch((err) => {
        console.warn("[SW] Cache addAll warning:", err);
      });
    })
  );
  self.skipWaiting();
});

// 2. التفعيل وحذف أي كاش قديم معلق
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log("[SW] Deleting stale cache:", key);
            return caches.delete(key);
          }
        })
      )
    ).then(() => self.clients.claim())
  );
});

// 3. التحكم في رسائل الصفحة (لمسح الكاش عند الحاجة)
self.addEventListener("message", (event) => {
  if (event.data && event.data.action === "clearCache") {
    caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k))));
  }
});

// 4. استرجاع الملفات مع استثناء كامل لسيرفر البايثون المحلي والـ API وسحابة جوجل
self.addEventListener("fetch", (event) => {
  const url = event.request.url;

  // عدم اعتراض أي طلبات موجهة لسيرفر البايثون المحلي أو الـ API أو Google Apps Script
  if (
    event.request.method !== "GET" ||
    url.includes("127.0.0.1") ||
    url.includes("localhost") ||
    url.includes("/api/") ||
    url.includes("script.google.com") ||
    url.includes("script.googleusercontent.com")
  ) {
    return;
  }

  // استراتيجية Network First للملفات لضمان التحديث اللحظي للكود
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const resClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, resClone));
        }
        return networkResponse;
      })
      .catch(() => caches.match(event.request))
  );
});
