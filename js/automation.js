// =========================================================================
// Nusuk ERP Pro - Automation Engine & System Initializer (automation.js)
// =========================================================================

const API_BASE = "http://127.0.0.1:8000";
let pilgrimsList = [];
let isProcessing = false;
let stopRequested = false;

// 1. فحص حالة سيرفر البايثون المحلي وحالة المحاكي تلقائياً كل 3 ثواني
async function checkServerStatus() {
    const dot = document.getElementById("statusDot");
    const txt = document.getElementById("statusText");
    const badge = document.getElementById("serverStatusBadge");
    if (!dot || !txt || !badge) return;

    try {
        const res = await fetch(`${API_BASE}/api/status`);
        if (res.ok) {
            const data = await res.json().catch(() => ({}));
            dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-400";
            if (data.device_connected) {
                txt.textContent = "السيرفر متصل (المحاكي جاهز)";
            } else {
                txt.textContent = "السيرفر متصل (بانتظار المحاكي)";
            }
            txt.className = "text-[11px] text-emerald-400 font-bold";
            badge.className = "flex items-center gap-2 px-3 py-2 rounded-full bg-emerald-950/60 border border-emerald-500/40 text-xs font-bold";
            return;
        }
    } catch (e) {}

    dot.className = "w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse";
    txt.textContent = "السيرفر غير متصل";
    txt.className = "text-[11px] text-red-400";
    badge.className = "flex items-center gap-2 px-3 py-2 rounded-full bg-slate-800 border border-slate-700 text-xs font-bold";
}

// 2. إدارة إعدادات الجنسية وتمييز الزرار المختار باللون الأصفر الذهبي
function setNatPreset(countryText, optionVal) {
    document.getElementById("natText").value = countryText;
    document.getElementById("natOption").value = String(optionVal);
    saveNatSettings();
}

function saveNatSettings() {
    const text = document.getElementById("natText").value.trim();
    const opt = document.getElementById("natOption").value;
    localStorage.setItem("nusuk_nat_text", text);
    localStorage.setItem("nusuk_nat_opt", opt);
    highlightActiveNatButton(text, opt);
}

function highlightActiveNatButton(text, opt) {
    const btnThailand = document.getElementById("btnNatThailand");
    const btnEgypt = document.getElementById("btnNatEgypt");
    const btnMorocco = document.getElementById("btnNatMorocco");
    if (!btnThailand || !btnEgypt || !btnMorocco) return;

    [btnThailand, btnEgypt, btnMorocco].forEach(btn => btn.classList.remove("nat-btn-active"));

    if (text === "تايلاند" && String(opt) === "1") {
        btnThailand.classList.add("nat-btn-active");
    } else if (text === "مصر" && String(opt) === "2") {
        btnEgypt.classList.add("nat-btn-active");
    } else if (text === "المغرب" && String(opt) === "1") {
        btnMorocco.classList.add("nat-btn-active");
    }
}

function loadNatSettings() {
    const savedText = localStorage.getItem("nusuk_nat_text") || "تايلاند";
    const savedOpt = localStorage.getItem("nusuk_nat_opt") || "1";
    const natTextEl = document.getElementById("natText");
    const natOptEl = document.getElementById("natOption");
    if (natTextEl) natTextEl.value = savedText;
    if (natOptEl) natOptEl.value = savedOpt;
    highlightActiveNatButton(savedText, savedOpt);
}

// 3. إدارة حسابات استلام OTP ومزامنتها مع السحابة لتعمل على كل أجهزتك
function togglePassVisibility() {
    const passInput = document.getElementById("clientPass");
    const icon = document.getElementById("passEyeIcon");
    if (passInput.type === "password") {
        passInput.type = "text";
        icon.className = "fa-solid fa-eye-slash";
    } else {
        passInput.type = "password";
        icon.className = "fa-solid fa-eye";
    }
}

function saveActiveCredentials() {
    localStorage.setItem("nusuk_active_email", document.getElementById("clientEmail").value.trim());
    localStorage.setItem("nusuk_active_pass", document.getElementById("clientPass").value.trim());
    const nusukPassEl = document.getElementById("nusukAccountPass");
    if (nusukPassEl) {
        localStorage.setItem("nusuk_account_pass", nusukPassEl.value.trim() || "Msamy2006**");
    }
}

function getSavedProfiles() {
    if (window.ERP_DB && Array.isArray(window.ERP_DB.profiles) && window.ERP_DB.profiles.length > 0) {
        return window.ERP_DB.profiles;
    }
    try {
        return JSON.parse(localStorage.getItem("nusuk_saved_profiles") || "[]");
    } catch {
        return [];
    }
}

function renderSavedProfiles() {
    const select = document.getElementById("savedProfilesSelect");
    if (!select) return;
    const profiles = getSavedProfiles();
    select.innerHTML = `<option value="">-- اختر حساباً محفوظاً (${profiles.length}) --</option>`;
    profiles.forEach((p, idx) => {
        const opt = document.createElement("option");
        opt.value = idx;
        opt.textContent = `${p.name} (${p.email})`;
        select.appendChild(opt);
    });
}

async function saveCurrentProfile() {
    const name = document.getElementById("profileName").value.trim() || "حساب بدون اسم";
    const email = document.getElementById("clientEmail").value.trim();
    const pass = document.getElementById("clientPass").value.trim();
    if (!email || !pass) {
        alert("يرجى كتابة الإيميل وكلمة مرور التطبيقات أولاً!");
        return;
    }
    const profiles = getSavedProfiles();
    const existingIdx = profiles.findIndex(p => p.email === email);
    if (existingIdx >= 0) {
        profiles[existingIdx] = { name, email, pass };
    } else {
        profiles.push({ name, email, pass });
    }

    window.ERP_DB.profiles = profiles;
    localStorage.setItem("nusuk_saved_profiles", JSON.stringify(profiles));
    saveActiveCredentials();
    renderSavedProfiles();
    await syncToCloud();
    alert("تم حفظ الحساب ومزامنته على السحابة بنجاح!");
}

function loadSelectedProfile() {
    const idx = document.getElementById("savedProfilesSelect").value;
    if (idx === "") return;
    const profiles = getSavedProfiles();
    const p = profiles[idx];
    if (p) {
        document.getElementById("profileName").value = p.name;
        document.getElementById("clientEmail").value = p.email;
        document.getElementById("clientPass").value = p.pass;
        saveActiveCredentials();
    }
}

async function deleteSelectedProfile() {
    const idx = document.getElementById("savedProfilesSelect").value;
    if (idx === "") return;
    const profiles = getSavedProfiles();
    profiles.splice(idx, 1);
    window.ERP_DB.profiles = profiles;
    localStorage.setItem("nusuk_saved_profiles", JSON.stringify(profiles));
    renderSavedProfiles();
    await syncToCloud();
}

// 4. قراءة شيت الإكسل للمعتمرين وإضافتهم لطابور الأتمتة
function extractFromRow(row, keys) {
    for (const k of Object.keys(row)) {
        const cleanK = k.trim().replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").toLowerCase();
        for (const sk of keys) {
            const cleanS = sk.trim().replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").toLowerCase();
            if (cleanK === cleanS || cleanK.includes(cleanS)) {
                return String(row[k]).trim();
            }
        }
    }
    return "";
}

function handleExcelUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        const data = new Uint8Array(e.target.result);
        const workbook = XLSX.read(data, { type: "array" });
        const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(firstSheet, { defval: "" });

        rows.forEach(row => {
            const passport = extractFromRow(row, ["رقم الجواز", "الجواز", "passport", "وثيقة"]);
            const visa = extractFromRow(row, ["رقم التأشيرة", "التأشيرة", "الفيزا", "تاشيره", "visa"]);
            const email = extractFromRow(row, ["البريد", "الايميل", "إيميل", "email"]);
            if (passport || visa) {
                pilgrimsList.push({
                    raw: row,
                    passport: passport,
                    visa: visa,
                    email: email,
                    otp: "-",
                    status: "pending",
                    message: "في الانتظار"
                });
            }
        });
        event.target.value = "";
        savePilgrimsToStorage();
        renderPilgrimsTable();
    };
    reader.readAsArrayBuffer(file);
}

function addManualPilgrim() {
    const passport = document.getElementById("manualPassport").value.trim();
    const visa = document.getElementById("manualVisa").value.trim();
    const email = document.getElementById("manualEmail").value.trim();
    if (!passport || !visa) {
        alert("يرجى إدخال رقم الجواز ورقم التأشيرة!");
        return;
    }
    pilgrimsList.push({
        raw: { "رقم الجواز": passport, "رقم التأشيرة": visa, "البريد الإلكتروني": email },
        passport,
        visa,
        email,
        otp: "-",
        status: "pending",
        message: "في الانتظار"
    });
    document.getElementById("manualPassport").value = "";
    document.getElementById("manualVisa").value = "";
    document.getElementById("manualEmail").value = "";
    savePilgrimsToStorage();
    renderPilgrimsTable();
}

// 5. عرض جدول المعتمرين والإحصائيات
function renderPilgrimsTable() {
    const tbody = document.getElementById("pilgrimsTableBody");
    if (!tbody) return;
    const clientEmail = document.getElementById("clientEmail")?.value.trim() || "";

    document.getElementById("statTotal").textContent = pilgrimsList.length;
    document.getElementById("statSuccess").textContent = pilgrimsList.filter(p => p.status === "completed").length;
    document.getElementById("statAlready").textContent = pilgrimsList.filter(p => p.status === "already_registered").length;
    document.getElementById("statError").textContent = pilgrimsList.filter(p => p.status === "error").length;

    if (pilgrimsList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="py-12 text-center text-slate-500 text-xs">لا توجد بيانات حالياً.. ارفع شيت الإكسل أو أضف معتمراً يدوياً للبدء</td></tr>`;
        return;
    }

    tbody.innerHTML = pilgrimsList.map((p, idx) => {
        let badge = `<span class="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 text-xs">في الانتظار</span>`;
        if (p.status === "processing") {
            badge = `<span class="px-2.5 py-1 rounded-lg bg-blue-500/20 text-blue-300 border border-blue-500/30 text-xs animate-pulse"><i class="fa-solid fa-spinner fa-spin ml-1"></i> جاري التسجيل...</span>`;
        } else if (p.status === "completed") {
            badge = `<span class="px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs"><i class="fa-solid fa-check ml-1"></i> تم التسجيل</span>`;
        } else if (p.status === "already_registered") {
            badge = `<span class="px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs"><i class="fa-solid fa-triangle-exclamation ml-1"></i> مسجل مسبقاً</span>`;
        } else if (p.status === "error") {
            badge = `<span title="${p.message}" class="px-2.5 py-1 rounded-lg bg-red-500/20 text-red-300 border border-red-500/30 text-xs"><i class="fa-solid fa-xmark ml-1"></i> ${p.message || "فشل"}</span>`;
        }

        return `
            <tr class="hover:bg-slate-800/40 transition">
                <td class="py-3 px-4 font-bold text-slate-400">${idx + 1}</td>
                <td class="py-3 px-4 font-mono text-amber-300" dir="ltr">${p.passport}</td>
                <td class="py-3 px-4 font-mono text-slate-200" dir="ltr">${p.visa}</td>
                <td class="py-3 px-4 text-xs text-slate-300" dir="ltr">${p.email || clientEmail || "-"}</td>
                <td class="py-3 px-4 font-mono font-bold text-emerald-400">${p.otp || "-"}</td>
                <td class="py-3 px-4">${badge}</td>
                <td class="py-3 px-4 text-center">
                    <div class="flex items-center justify-center gap-1">
                        <button onclick="processSinglePilgrim(${idx})" title="تشغيل هذا المعتمر" class="p-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600 text-emerald-400 hover:text-white transition text-xs">
                            <i class="fa-solid fa-play"></i>
                        </button>
                        <button onclick="removePilgrim(${idx})" title="حذف" class="p-1.5 rounded-lg bg-red-600/20 hover:bg-red-600 text-red-400 hover:text-white transition text-xs">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");
}

function removePilgrim(idx) {
    pilgrimsList.splice(idx, 1);
    savePilgrimsToStorage();
    renderPilgrimsTable();
}

function clearPilgrimList() {
    if (!confirm("هل أنت متأكد من مسح القائمة بالكامل؟")) return;
    pilgrimsList = [];
    savePilgrimsToStorage();
    renderPilgrimsTable();
}

function retryFailedPilgrims() {
    pilgrimsList.forEach(p => {
        if (p.status === "error") {
            p.status = "pending";
            p.message = "في الانتظار";
        }
    });
    savePilgrimsToStorage();
    renderPilgrimsTable();
}

function syncQueueToServer() {
    try {
        const payload = {
            nusuk_active_email: localStorage.getItem("nusuk_active_email") || document.getElementById("clientEmail")?.value.trim() || "",
            nusuk_active_pass: localStorage.getItem("nusuk_active_pass") || document.getElementById("clientPass")?.value.trim() || "",
            nusuk_account_pass: localStorage.getItem("nusuk_account_pass") || document.getElementById("nusukAccountPass")?.value.trim() || "Msamy2006**",
            nusuk_nat_text: localStorage.getItem("nusuk_nat_text") || document.getElementById("natText")?.value.trim() || "تايلاند",
            nusuk_nat_opt: localStorage.getItem("nusuk_nat_opt") || document.getElementById("natOption")?.value || "1",
            pilgrimsList: pilgrimsList
        };
        fetch(`${API_BASE}/api/sync_queue`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        }).catch(() => {});
    } catch (e) {}
}

function savePilgrimsToStorage() {
    localStorage.setItem("nusuk_pilgrims_queue", JSON.stringify(pilgrimsList));
    syncQueueToServer();
}

// 6. تشغيل الأتمتة وإرسال الجنسية المختارة إلى السيرفر
async function processSinglePilgrim(idx) {
    const clientEmail = document.getElementById("clientEmail").value.trim();
    const clientPass = document.getElementById("clientPass").value.trim();
    if (!clientEmail || !clientPass) {
        alert("يرجى إدخال إيميل العميل وكلمة مرور التطبيقات (16 حرف) أولاً!");
        return false;
    }

    const p = pilgrimsList[idx];
    p.status = "processing";
    renderPilgrimsTable();

    const natText = document.getElementById("natText").value.trim() || "تايلاند";
    const natOpt = document.getElementById("natOption").value;
    const natY = natOpt === "2" ? 275 : 195;

    const nusukPass = document.getElementById("nusukAccountPass")?.value.trim() || "Msamy2006**";

    try {
        const res = await fetch(`${API_BASE}/api/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                client_email: clientEmail,
                client_pass: clientPass,
                nusuk_password: nusukPass,
                nationality: natText,
                nationality_y: natY,
                pilgrim: {
                    ...p.raw,
                    "رقم الجواز": p.passport,
                    "رقم التأشيرة": p.visa,
                    "email": p.email || clientEmail,
                    "الباسورد": nusukPass
                }
            })
        });
        const data = await res.json();
        if (data.status === "completed" || data.success) {
            p.status = "completed";
            p.otp = data.otp || p.otp;
            p.message = "تم التسجيل بنجاح";
        } else if (data.status === "already_registered") {
            p.status = "already_registered";
            p.message = "مسجل مسبقاً";
        } else {
            p.status = "error";
            p.message = data.error || data.message || "خطأ أثناء التنفيذ";
        }
    } catch (err) {
        p.status = "error";
        p.message = "تعذر الاتصال بالسيرفر";
    }

    savePilgrimsToStorage();
    renderPilgrimsTable();
    return true;
}

async function startQueueProcessing() {
    if (isProcessing) return;
    const clientEmail = document.getElementById("clientEmail").value.trim();
    const clientPass = document.getElementById("clientPass").value.trim();
    if (!clientEmail || !clientPass) {
        alert("يرجى إدخال إيميل العميل وكلمة مرور التطبيقات أولاً!");
        return;
    }

    isProcessing = true;
    stopRequested = false;
    document.getElementById("btnStartQueue").disabled = true;
    document.getElementById("btnStopQueue").disabled = false;

    for (let i = 0; i < pilgrimsList.length; i++) {
        if (stopRequested) break;
        if (pilgrimsList[i].status === "pending") {
            await processSinglePilgrim(i);
        }
    }

    isProcessing = false;
    document.getElementById("btnStartQueue").disabled = false;
    document.getElementById("btnStopQueue").disabled = true;
}

function stopQueueProcessing() {
    stopRequested = true;
}

// 7. تصدير تقرير الأتمتة إلى Excel
function exportResultsToExcel() {
    if (pilgrimsList.length === 0) {
        alert("لا توجد بيانات لتصديرها!");
        return;
    }
    const exportData = pilgrimsList.map((p, i) => ({
        "#": i + 1,
        "رقم الجواز": p.passport,
        "رقم التأشيرة": p.visa,
        "الإيميل": p.email || document.getElementById("clientEmail").value.trim(),
        "كود OTP": p.otp,
        "الحالة": p.message
    }));
    const ws = XLSX.utils.json_to_sheet(exportData);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "تقرير نسك");
    XLSX.writeFile(wb, `Nusuk_Report_${new Date().toISOString().slice(0, 10)}.xlsx`);
}

// =========================================================================
// 8. التنقل بين الصفحات الثلاث وتثبيت الـ PWA
// =========================================================================
function switchPage(pageName) {
    const pageAutomation = document.getElementById("pageAutomation");
    const pageCalendar = document.getElementById("pageCalendar");
    const pageAccounting = document.getElementById("pageAccounting");

    const tabBtnAutomation = document.getElementById("tabBtnAutomation");
    const tabBtnCalendar = document.getElementById("tabBtnCalendar");
    const tabBtnAccounting = document.getElementById("tabBtnAccounting");

    if (pageAutomation) pageAutomation.classList.add("hidden");
    if (pageCalendar) pageCalendar.classList.add("hidden");
    if (pageAccounting) pageAccounting.classList.add("hidden");

    [tabBtnAutomation, tabBtnCalendar, tabBtnAccounting].forEach(btn => {
        if (btn) {
            btn.classList.remove("nav-tab-active");
            btn.classList.add("text-slate-300");
        }
    });

    if (pageName === "automation") {
        if (pageAutomation) pageAutomation.classList.remove("hidden");
        if (tabBtnAutomation) {
            tabBtnAutomation.classList.add("nav-tab-active");
            tabBtnAutomation.classList.remove("text-slate-300");
        }
    } else if (pageName === "calendar") {
        if (pageCalendar) pageCalendar.classList.remove("hidden");
        if (tabBtnCalendar) {
            tabBtnCalendar.classList.add("nav-tab-active");
            tabBtnCalendar.classList.remove("text-slate-300");
        }
        if (typeof window.renderCalendarGrid === "function") window.renderCalendarGrid();
        if (typeof window.renderTripsTable === "function") window.renderTripsTable();
    } else if (pageName === "accounting") {
        if (pageAccounting) pageAccounting.classList.remove("hidden");
        if (tabBtnAccounting) {
            tabBtnAccounting.classList.add("nav-tab-active");
            tabBtnAccounting.classList.remove("text-slate-300");
        }
        if (typeof window.renderSelectedClientAccounting === "function") window.renderSelectedClientAccounting();
    }
}

let deferredPrompt = null;
if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("beforeinstallprompt", (e) => {
        e.preventDefault();
        deferredPrompt = e;
        const btn = document.getElementById("btnInstallApp");
        if (btn) btn.classList.remove("hidden");
    });
}

function installPWA() {
    if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(() => {
            deferredPrompt = null;
            const btn = document.getElementById("btnInstallApp");
            if (btn) btn.classList.add("hidden");
        });
    } else {
        alert("تطبيق الويب مثبت بالفعل أو يمكنك تثبيته مباشرة من شريط خيارات المتصفح.");
    }
}

// 9. تهيئة النظام بالكامل عند فتح التطبيق من أي جهاز
if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("DOMContentLoaded", async () => {
        if (typeof window.loadLocalDatabase === "function") window.loadLocalDatabase();
        if (typeof window.refreshAllViews === "function") window.refreshAllViews();

        const clientEmail = document.getElementById("clientEmail");
        const clientPass = document.getElementById("clientPass");
        const nusukAccountPass = document.getElementById("nusukAccountPass");
        if (clientEmail) clientEmail.value = localStorage.getItem("nusuk_active_email") || "";
        if (clientPass) clientPass.value = localStorage.getItem("nusuk_active_pass") || "";
        if (nusukAccountPass) nusukAccountPass.value = localStorage.getItem("nusuk_account_pass") || "Msamy2006**";

        renderSavedProfiles();
        loadNatSettings();

        try {
            pilgrimsList = JSON.parse(localStorage.getItem("nusuk_pilgrims_queue") || "[]");
        } catch {
            pilgrimsList = [];
        }
        renderPilgrimsTable();
        syncQueueToServer();

        // فحص سيرفر البايثون المحلي
        checkServerStatus();
        setInterval(checkServerStatus, 3000);

        // مزامنة تلقائية مع Google Drive عند الفتح
        if (typeof window.syncFromCloud === "function") {
            await window.syncFromCloud(false);
        }
    });
}

// =========================================================================
// ربط جميع الدوال صراحة بـ window لضمان عمل onclick في HTML بدون أي أخطاء
// =========================================================================
window.syncQueueToServer = syncQueueToServer;
window.checkServerStatus = checkServerStatus;
window.setNatPreset = setNatPreset;
window.saveNatSettings = saveNatSettings;
window.highlightActiveNatButton = highlightActiveNatButton;
window.loadNatSettings = loadNatSettings;
window.togglePassVisibility = togglePassVisibility;
window.saveActiveCredentials = saveActiveCredentials;
window.getSavedProfiles = getSavedProfiles;
window.renderSavedProfiles = renderSavedProfiles;
window.saveCurrentProfile = saveCurrentProfile;
window.loadSelectedProfile = loadSelectedProfile;
window.deleteSelectedProfile = deleteSelectedProfile;
window.extractFromRow = extractFromRow;
window.handleExcelUpload = handleExcelUpload;
window.addManualPilgrim = addManualPilgrim;
window.renderPilgrimsTable = renderPilgrimsTable;
window.removePilgrim = removePilgrim;
window.clearPilgrimList = clearPilgrimList;
window.retryFailedPilgrims = retryFailedPilgrims;
window.savePilgrimsToStorage = savePilgrimsToStorage;
window.processSinglePilgrim = processSinglePilgrim;
window.startQueueProcessing = startQueueProcessing;
window.stopQueueProcessing = stopQueueProcessing;
window.exportResultsToExcel = exportResultsToExcel;
window.switchPage = switchPage;
window.installPWA = installPWA;

