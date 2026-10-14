// =========================================================================
// Nusuk ERP Pro - Cloud API & Local Database Synchronizer (cloud-api.js)
// يدعم Google Apps Script و Google Drive وقاعدة البيانات المحلية
// =========================================================================

// قاعدة البيانات المركزية في الذاكرة
window.ERP_DB = window.ERP_DB || {
    clients: [],
    trips: [],
    rosters: [],
    payments: [],
    profiles: []
};

// مفاتيح التخزين المحلي
const STORAGE_KEY_DB = "nusuk_erp_db";
const STORAGE_KEY_GAS = "nusuk_gas_url";

// 1. تحميل قاعدة البيانات من التخزين المحلي
function loadLocalDatabase() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY_DB);
        if (raw) {
            const parsed = JSON.parse(raw);
            window.ERP_DB = {
                clients: Array.isArray(parsed.clients) ? parsed.clients : [],
                trips: Array.isArray(parsed.trips) ? parsed.trips : [],
                rosters: Array.isArray(parsed.rosters) ? parsed.rosters : [],
                payments: Array.isArray(parsed.payments) ? parsed.payments : [],
                profiles: Array.isArray(parsed.profiles) ? parsed.profiles : []
            };
        }
    } catch (err) {
        console.warn("[CloudAPI] Error loading local DB:", err);
    }
    return window.ERP_DB;
}

// 2. حفظ قاعدة البيانات في التخزين المحلي
function saveLocalDatabase() {
    try {
        if (!window.ERP_DB) {
            window.ERP_DB = { clients: [], trips: [], rosters: [], payments: [], profiles: [] };
        }
        localStorage.setItem(STORAGE_KEY_DB, JSON.stringify(window.ERP_DB));
    } catch (err) {
        console.warn("[CloudAPI] Error saving local DB:", err);
    }
}

// 3. مزامنة البيانات من سحابة Google Drive / Apps Script
async function syncFromCloud(manual = false) {
    const icon = document.getElementById("cloudSyncIcon");
    const txt = document.getElementById("cloudStatusText");

    if (icon) icon.className = "fa-solid fa-cloud-arrow-down animate-bounce";
    if (txt) txt.textContent = "جاري التحديث...";

    const gasUrl = localStorage.getItem(STORAGE_KEY_GAS) || "";

    if (!gasUrl) {
        if (icon) icon.className = "fa-solid fa-cloud text-amber-400";
        if (txt) txt.textContent = "متصل محلياً";
        if (manual) {
            const promptUrl = prompt(
                "البيانات محفوظة محلياً بنجاح.\nإذا كان لديك رابط Google Apps Script Web App لمزامنة كشوفات الدرايف، أدخله هنا (أو اتركه فارغاً):",
                ""
            );
            if (promptUrl && promptUrl.trim().startsWith("http")) {
                localStorage.setItem(STORAGE_KEY_GAS, promptUrl.trim());
                alert("تم حفظ رابط السحابة بنجاح! سيتم المزامنة الآن.");
                return syncFromCloud(false);
            }
        }
        return true;
    }

    try {
        const res = await fetch(`${gasUrl}?action=getDatabase&t=${Date.now()}`);
        if (res.ok) {
            const data = await res.json();
            if (data && typeof data === "object") {
                if (Array.isArray(data.clients) && data.clients.length > 0) window.ERP_DB.clients = data.clients;
                if (Array.isArray(data.trips)) window.ERP_DB.trips = data.trips;
                if (Array.isArray(data.rosters)) window.ERP_DB.rosters = data.rosters;
                if (Array.isArray(data.payments)) window.ERP_DB.payments = data.payments;
                if (Array.isArray(data.profiles)) window.ERP_DB.profiles = data.profiles;

                saveLocalDatabase();
                if (typeof window.refreshAllViews === "function") window.refreshAllViews();
                if (typeof window.renderSavedProfiles === "function") window.renderSavedProfiles();

                if (icon) icon.className = "fa-solid fa-cloud text-emerald-400";
                if (txt) txt.textContent = "متصل بالدرايف";
                if (manual) alert("✅ تمت المزامنة مع Google Drive بنجاح!");
                return true;
            }
        }
    } catch (err) {
        console.warn("[CloudAPI] GAS fetch error, fallback to local:", err);
    }

    if (icon) icon.className = "fa-solid fa-cloud text-amber-400";
    if (txt) txt.textContent = "متصل محلياً";
    if (manual) alert("تعذر الاتصال بسيرفر Google حالياً، البيانات تعمل من النسخة المحلية.");
    return false;
}

// 4. رفع وتحديث البيانات في سحابة Google Drive / Apps Script
async function syncToCloud() {
    saveLocalDatabase();
    const gasUrl = localStorage.getItem(STORAGE_KEY_GAS) || "";
    if (!gasUrl) return;

    try {
        await fetch(gasUrl, {
            method: "POST",
            mode: "no-cors",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                action: "saveDatabase",
                data: window.ERP_DB,
                timestamp: new Date().toISOString()
            })
        });
    } catch (err) {
        console.warn("[CloudAPI] Cloud push failed:", err);
    }
}

// 5. رفع ملف كشف العميل إلى مجلد العميل على Google Drive
async function uploadFileToClientDrive(file, clientName) {
    if (!file) return "";
    const gasUrl = localStorage.getItem(STORAGE_KEY_GAS) || "";

    const toBase64 = f => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(f);
        reader.onload = () => resolve(reader.result);
        reader.onerror = error => reject(error);
    });

    try {
        const base64Data = await toBase64(file);
        if (gasUrl) {
            const res = await fetch(gasUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    action: "uploadFile",
                    clientName: clientName || "عام",
                    fileName: file.name,
                    fileData: base64Data
                })
            });
            const result = await res.json();
            if (result && result.driveUrl) {
                return result.driveUrl;
            }
        }
        return URL.createObjectURL(file);
    } catch (err) {
        console.warn("[CloudAPI] Drive upload fallback:", err);
        return URL.createObjectURL(file);
    }
}

// ربط جميع الدوال صراحة بـ window
window.ERP_DB = window.ERP_DB;
window.loadLocalDatabase = loadLocalDatabase;
window.saveLocalDatabase = saveLocalDatabase;
window.syncFromCloud = syncFromCloud;
window.syncToCloud = syncToCloud;
window.uploadFileToClientDrive = uploadFileToClientDrive;
