// =========================================================================
// Nusuk ERP Pro - Smart Rawdah Planner, Calendar & Accounting Engine
// مدمج بالكامل مع كافة بيانات شيت (حسابات الروضة - محمد سامي - 1448 هـ)
// =========================================================================

const INITIAL_EXCEL_CLIENTS = [
    {"id": "c1", "name": "طواف للسياحة", "rate": 50},
    {"id": "c2", "name": "الحاج وائل الفارسي السعودية", "rate": 50},
    {"id": "c3", "name": "عصام كيلاسينا", "rate": 30},
    {"id": "c4", "name": "عصام الطبيعة", "rate": 40},
    {"id": "c5", "name": "مصطفى فرصة للسياحة", "rate": 40},
    {"id": "c6", "name": "احمد سمير", "rate": 40},
    {"id": "c7", "name": "كيان للسياحة", "rate": 40},
    {"id": "c8", "name": "محمود أبو زيد", "rate": 40},
    {"id": "c9", "name": "اسامه عبداللة", "rate": 30},
    {"id": "c10", "name": "محمد قاسم", "rate": 30},
    {"id": "c11", "name": "الحج مجدي", "rate": 40},
    {"id": "c12", "name": "عبد الرحمن صلاح", "rate": 40},
    {"id": "c13", "name": "النخبه", "rate": 40},
    {"id": "c14", "name": "الحج منعم", "rate": 40},
    {"id": "c15", "name": "الفتح", "rate": 30}
];

const INITIAL_EXCEL_ROSTERS = [
    {"id": "r1", "clientId": "c1", "date": "3/8/2026", "code": "", "count": 43, "price": 2150, "paidGreen": true, "driveUrl": ""},
    {"id": "r2", "clientId": "c1", "date": "14/8/2026", "code": "", "count": 45, "price": 2250, "paidGreen": true, "driveUrl": ""},
    {"id": "r3", "clientId": "c1", "date": "17/8/2026", "code": "", "count": 44, "price": 2200, "paidGreen": true, "driveUrl": ""},
    {"id": "r4", "clientId": "c1", "date": "18/8/2026", "code": "", "count": 45, "price": 2250, "paidGreen": true, "driveUrl": ""},
    {"id": "r5", "clientId": "c1", "date": "19/8/2026", "code": "", "count": 49, "price": 2450, "paidGreen": true, "driveUrl": ""},
    {"id": "r6", "clientId": "c1", "date": "27/8/2026", "code": "", "count": 44, "price": 2200, "paidGreen": true, "driveUrl": ""},
    {"id": "r7", "clientId": "c1", "date": "23/8/2026", "code": "", "count": 45, "price": 2250, "paidGreen": true, "driveUrl": ""},
    {"id": "r8", "clientId": "c1", "date": "30/8/2026", "code": "", "count": 44, "price": 2200, "paidGreen": true, "driveUrl": ""},
    {"id": "r9", "clientId": "c1", "date": "5/9/2026", "code": "", "count": 40, "price": 2000, "paidGreen": false, "driveUrl": ""},
    {"id": "r10", "clientId": "c1", "date": "13/9/2026", "code": "", "count": 45, "price": 2250, "paidGreen": false, "driveUrl": ""},
    {"id": "r11", "clientId": "c1", "date": "23/9/2026", "code": "", "count": 41, "price": 2050, "paidGreen": false, "driveUrl": ""},
    {"id": "r12", "clientId": "c1", "date": "25/9/2026", "code": "", "count": 89, "price": 4450, "paidGreen": false, "driveUrl": ""},
    {"id": "r13", "clientId": "c1", "date": "2/10/2026", "code": "", "count": 44, "price": 2200, "paidGreen": false, "driveUrl": ""},
    {"id": "r14", "clientId": "c1", "date": "5/10/2026", "code": "", "count": 47, "price": 2350, "paidGreen": false, "driveUrl": ""},
    {"id": "r15", "clientId": "c1", "date": "9/10/2026", "code": "", "count": 39, "price": 1950, "paidGreen": false, "driveUrl": ""},
    {"id": "r16", "clientId": "c2", "date": "13/8/2026", "code": "", "count": 23, "price": 1150, "paidGreen": true, "driveUrl": ""},
    {"id": "r17", "clientId": "c2", "date": "17/8/2026", "code": "", "count": 30, "price": 1500, "paidGreen": true, "driveUrl": ""},
    {"id": "r18", "clientId": "c2", "date": "20/8/2026", "code": "", "count": 45, "price": 2250, "paidGreen": true, "driveUrl": ""},
    {"id": "r19", "clientId": "c2", "date": "28/9/2026", "code": "", "count": 20, "price": 1000, "paidGreen": false, "driveUrl": ""},
    {"id": "r20", "clientId": "c2", "date": "3/10/2026", "code": "alyaa company", "count": 24, "price": 1200, "paidGreen": false, "driveUrl": ""},
    {"id": "r21", "clientId": "c2", "date": "4/10/2026", "code": "HYY12", "count": 47, "price": 2350, "paidGreen": false, "driveUrl": ""},
    {"id": "r22", "clientId": "c2", "date": "9/10/2026", "code": "HYT14", "count": 45, "price": 2250, "paidGreen": false, "driveUrl": ""},
    {"id": "r23", "clientId": "c2", "date": "11/10/2026", "code": "ustaz ibrahim", "count": 37, "price": 1850, "paidGreen": false, "driveUrl": ""},
    {"id": "r24", "clientId": "c2", "date": "11/10/2026", "code": "HYT16", "count": 27, "price": 1350, "paidGreen": false, "driveUrl": ""},
    {"id": "r25", "clientId": "c2", "date": "13/10/2026", "code": "HYT25", "count": 44, "price": 2200, "paidGreen": false, "driveUrl": ""},
    {"id": "r26", "clientId": "c2", "date": "14/10/2026", "code": "HYT18", "count": 45, "price": 2250, "paidGreen": false, "driveUrl": ""},
    {"id": "r27", "clientId": "c2", "date": "14/10/2026", "code": "HYT22", "count": 48, "price": 2400, "paidGreen": false, "driveUrl": ""},
    {"id": "r28", "clientId": "c3", "date": "11/8/2026", "code": "", "count": 40, "price": 1200, "paidGreen": true, "driveUrl": ""},
    {"id": "r29", "clientId": "c3", "date": "15/8/2026", "code": "", "count": 40, "price": 1200, "paidGreen": true, "driveUrl": ""},
    {"id": "r30", "clientId": "c3", "date": "16/8/2026", "code": "", "count": 47, "price": 1410, "paidGreen": true, "driveUrl": ""},
    {"id": "r31", "clientId": "c3", "date": "24/8/2026", "code": "", "count": 40, "price": 1200, "paidGreen": true, "driveUrl": ""},
    {"id": "r32", "clientId": "c3", "date": "23/8/2026", "code": "", "count": 45, "price": 1350, "paidGreen": true, "driveUrl": ""},
    {"id": "r33", "clientId": "c3", "date": "29/8/2026", "code": "", "count": 38, "price": 1140, "paidGreen": true, "driveUrl": ""},
    {"id": "r34", "clientId": "c3", "date": "1/9/2026", "code": "", "count": 45, "price": 1350, "paidGreen": true, "driveUrl": ""},
    {"id": "r35", "clientId": "c3", "date": "10/9/2026", "code": "", "count": 20, "price": 600, "paidGreen": true, "driveUrl": ""},
    {"id": "r36", "clientId": "c3", "date": "17/9/2026", "code": "", "count": 43, "price": 1290, "paidGreen": false, "driveUrl": ""},
    {"id": "r37", "clientId": "c3", "date": "مكس", "code": "مكس", "count": 5, "price": 150, "paidGreen": false, "driveUrl": ""},
    {"id": "r38", "clientId": "c4", "date": "10/8/2026", "code": "", "count": 84, "price": 3360, "paidGreen": true, "driveUrl": ""},
    {"id": "r39", "clientId": "c4", "date": "17/8/2026", "code": "", "count": 88, "price": 3520, "paidGreen": true, "driveUrl": ""},
    {"id": "r40", "clientId": "c4", "date": "21/8/2026", "code": "", "count": 90, "price": 3600, "paidGreen": true, "driveUrl": ""},
    {"id": "r41", "clientId": "c4", "date": "27/8/2026", "code": "", "count": 40, "price": 1600, "paidGreen": false, "driveUrl": ""},
    {"id": "r42", "clientId": "c4", "date": "18/9/2026", "code": "", "count": 30, "price": 1200, "paidGreen": false, "driveUrl": ""},
    {"id": "r43", "clientId": "c4", "date": "25/9/2026", "code": "", "count": 15, "price": 600, "paidGreen": false, "driveUrl": ""},
    {"id": "r44", "clientId": "c4", "date": "7/10/2026", "code": "", "count": 9, "price": 360, "paidGreen": false, "driveUrl": ""},
    {"id": "r45", "clientId": "c4", "date": "8/10/2026", "code": "", "count": 22, "price": 880, "paidGreen": false, "driveUrl": ""},
    {"id": "r46", "clientId": "c5", "date": "8/3/2026", "code": "", "count": 22, "price": 880, "paidGreen": true, "driveUrl": ""},
    {"id": "r47", "clientId": "c5", "date": "8/8/2026", "code": "", "count": 52, "price": 2080, "paidGreen": true, "driveUrl": ""},
    {"id": "r48", "clientId": "c5", "date": "9/8/2026", "code": "", "count": 36, "price": 1440, "paidGreen": true, "driveUrl": ""},
    {"id": "r49", "clientId": "c5", "date": "25/8/2026", "code": "", "count": 42, "price": 1680, "paidGreen": true, "driveUrl": ""},
    {"id": "r50", "clientId": "c5", "date": "27/8/2026", "code": "", "count": 39, "price": 1560, "paidGreen": true, "driveUrl": ""},
    {"id": "r51", "clientId": "c6", "date": "5/8/2026", "code": "", "count": 74, "price": 2960, "paidGreen": false, "driveUrl": ""},
    {"id": "r52", "clientId": "c7", "date": "27/8/2026", "code": "", "count": 80, "price": 3200, "paidGreen": false, "driveUrl": ""},
    {"id": "r53", "clientId": "c7", "date": "29/8/2026", "code": "", "count": 50, "price": 2000, "paidGreen": false, "driveUrl": ""},
    {"id": "r54", "clientId": "c7", "date": "29/8/2026", "code": "", "count": 45, "price": 1800, "paidGreen": false, "driveUrl": ""},
    {"id": "r55", "clientId": "c7", "date": "29/8/2026", "code": "", "count": 43, "price": 1720, "paidGreen": false, "driveUrl": ""},
    {"id": "r56", "clientId": "c7", "date": "4/9/2026", "code": "", "count": 45, "price": 1800, "paidGreen": false, "driveUrl": ""},
    {"id": "r58", "clientId": "c8", "date": "2/9/2026", "code": "", "count": 39, "price": 1560, "paidGreen": false, "driveUrl": ""},
    {"id": "r59", "clientId": "c8", "date": "مجمع", "code": "مجمع", "count": 11, "price": 440, "paidGreen": false, "driveUrl": ""},
    {"id": "r60", "clientId": "c8", "date": "مجمع", "code": "مجمع", "count": 6, "price": 240, "paidGreen": false, "driveUrl": ""},
    {"id": "r61", "clientId": "c8", "date": "26/9/2026", "code": "", "count": 49, "price": 1960, "paidGreen": false, "driveUrl": ""},
    {"id": "r62", "clientId": "c8", "date": "3/10/2026", "code": "", "count": 82, "price": 3280, "paidGreen": false, "driveUrl": ""},
    {"id": "r63", "clientId": "c8", "date": "3/10/2026", "code": "", "count": 40, "price": 1600, "paidGreen": false, "driveUrl": ""},
    {"id": "r64", "clientId": "c9", "date": "13/8/2026", "code": "", "count": 65, "price": 1950, "paidGreen": false, "driveUrl": ""},
    {"id": "r65", "clientId": "c10", "date": "13/8/2026", "code": "", "count": 43, "price": 1290, "paidGreen": false, "driveUrl": ""},
    {"id": "r66", "clientId": "c10", "date": "26/8/2026", "code": "", "count": 44, "price": 1320, "paidGreen": false, "driveUrl": ""},
    {"id": "r67", "clientId": "c11", "date": "19/8/2026", "code": "", "count": 45, "price": 1800, "paidGreen": false, "driveUrl": ""},
    {"id": "r68", "clientId": "c11", "date": "20/8/2026", "code": "", "count": 44, "price": 1760, "paidGreen": false, "driveUrl": ""},
    {"id": "r69", "clientId": "c12", "date": "12/9/2026", "code": "مجموعة 1 سبتمبر", "count": 29, "price": 1160, "paidGreen": false, "driveUrl": ""},
    {"id": "r70", "clientId": "c12", "date": "14/9/2026", "code": "مجموعة دخول مدينه 12 سبتمبر", "count": 20, "price": 800, "paidGreen": false, "driveUrl": ""},
    {"id": "r71", "clientId": "c12", "date": "15/9/2026", "code": "المشرف عبدالرحمن صلاح", "count": 8, "price": 320, "paidGreen": false, "driveUrl": ""},
    {"id": "r72", "clientId": "c13", "date": "26/8/2026", "code": "", "count": 39, "price": 1560, "paidGreen": false, "driveUrl": ""},
    {"id": "r73", "clientId": "c13", "date": "31/8/2026", "code": "", "count": 17, "price": 680, "paidGreen": false, "driveUrl": ""},
    {"id": "r74", "clientId": "c14", "date": "18/8/2026", "code": "", "count": 41, "price": 1640, "paidGreen": false, "driveUrl": ""},
    {"id": "r75", "clientId": "c14", "date": "27/8/2026", "code": "", "count": 44, "price": 1760, "paidGreen": false, "driveUrl": ""},
    {"id": "r76", "clientId": "c14", "date": "2/9/2026", "code": "فرحات", "count": 46, "price": 1840, "paidGreen": false, "driveUrl": ""},
    {"id": "r77", "clientId": "c14", "date": "2/9/2026", "code": "برعصي", "count": 47, "price": 1880, "paidGreen": false, "driveUrl": ""},
    {"id": "r78", "clientId": "c14", "date": "2/9/2026", "code": "حمدي", "count": 45, "price": 1800, "paidGreen": false, "driveUrl": ""},
    {"id": "r79", "clientId": "c14", "date": "2/9/2026", "code": "بحيري", "count": 45, "price": 1800, "paidGreen": false, "driveUrl": ""},
    {"id": "r80", "clientId": "c14", "date": "4/9/2026", "code": "شعراوي", "count": 50, "price": 2000, "paidGreen": false, "driveUrl": ""},
    {"id": "r81", "clientId": "c14", "date": "10/9/2026", "code": "جمعة", "count": 45, "price": 1800, "paidGreen": false, "driveUrl": ""},
    {"id": "r82", "clientId": "c14", "date": "12/9/2026", "code": "حمدي", "count": 43, "price": 1720, "paidGreen": false, "driveUrl": ""},
    {"id": "r83", "clientId": "c14", "date": "14/9/2026", "code": "رحلة 12", "count": 45, "price": 1800, "paidGreen": false, "driveUrl": ""},
    {"id": "r84", "clientId": "c15", "date": "", "code": "vip", "count": 17, "price": 510, "paidGreen": false, "driveUrl": ""},
    {"id": "r85", "clientId": "c15", "date": "26/8/2026", "code": "", "count": 45, "price": 1350, "paidGreen": false, "driveUrl": ""},
    {"id": "r86", "clientId": "c15", "date": "7/9/2026", "code": "", "count": 50, "price": 1500, "paidGreen": false, "driveUrl": ""},
    {"id": "r87", "clientId": "c15", "date": "22/9/2026", "code": "", "count": 34, "price": 1020, "paidGreen": false, "driveUrl": ""}
];

const INITIAL_EXCEL_PAYMENTS = [
    {"id": "p1", "clientId": "c1", "date": "19/8/2026", "amount": 11300, "note": "دفعة مسجلة من الشيت"},
    {"id": "p2", "clientId": "c1", "date": "-", "amount": 6650, "note": "دفعة مسجلة من الشيت"},
    {"id": "p3", "clientId": "c2", "date": "4/9/2026", "amount": 4900, "note": "دفعة مسجلة من الشيت"},
    {"id": "p4", "clientId": "c3", "date": "17/8/2026", "amount": 3810, "note": "دفعة مسجلة من الشيت"},
    {"id": "p5", "clientId": "c3", "date": "14/9/2026", "amount": 5640, "note": "دفعة مسجلة من الشيت"},
    {"id": "p6", "clientId": "c3", "date": "-", "amount": 1440, "note": "دفعة مسجلة من الشيت"},
    {"id": "p7", "clientId": "c4", "date": "20/8/2026", "amount": 10480, "note": "دفعة مسجلة من الشيت"},
    {"id": "p8", "clientId": "c5", "date": "4/8/2026", "amount": 880, "note": "دفعة مسجلة من الشيت"},
    {"id": "p9", "clientId": "c5", "date": "10/8/2026", "amount": 3520, "note": "دفعة مسجلة من الشيت"},
    {"id": "p10", "clientId": "c5", "date": "31/8/2026", "amount": 3240, "note": "دفعة مسجلة من الشيت"},
    {"id": "p11", "clientId": "c6", "date": "5/8/2026", "amount": 2960, "note": "دفعة مسجلة من الشيت"},
    {"id": "p12", "clientId": "c7", "date": "20/8/2026", "amount": 3200, "note": "دفعة مسجلة من الشيت"},
    {"id": "p13", "clientId": "c7", "date": "29/8/2026", "amount": 9200, "note": "دفعة مسجلة من الشيت"},
    {"id": "p14", "clientId": "c8", "date": "-", "amount": 2000, "note": "دفعة مسجلة من الشيت"},
    {"id": "p15", "clientId": "c9", "date": "16/8/2026", "amount": 1950, "note": "دفعة مسجلة من الشيت"},
    {"id": "p16", "clientId": "c10", "date": "27/8/2026", "amount": 2610, "note": "دفعة مسجلة من الشيت"},
    {"id": "p17", "clientId": "c11", "date": "20/8/2026", "amount": 3560, "note": "دفعة مسجلة من الشيت"},
    {"id": "p18", "clientId": "c15", "date": "16/8/2026", "amount": 1950, "note": "دفعة مسجلة من الشيت"}
];

window.ERP_DB = window.ERP_DB || {
    clients: [],
    trips: [],
    rosters: [],
    payments: [],
    profiles: []
};

let currentCalendarDate = new Date();
let activeTripStatusFilter = "all";

// دمج بيانات الشيت الأصلية في قاعدة البيانات إذا لم تكن محملة بعد
function ensureInitialExcelDataLoaded() {
    if (!window.ERP_DB) {
        window.ERP_DB = { clients: [], trips: [], rosters: [], payments: [], profiles: [] };
    }
    if (!Array.isArray(window.ERP_DB.clients) || window.ERP_DB.clients.length < 10) {
        window.ERP_DB.clients = [...INITIAL_EXCEL_CLIENTS];
    }
    if (!Array.isArray(window.ERP_DB.rosters) || window.ERP_DB.rosters.length === 0) {
        window.ERP_DB.rosters = [...INITIAL_EXCEL_ROSTERS];
    }
    if (!Array.isArray(window.ERP_DB.payments) || window.ERP_DB.payments.length === 0) {
        window.ERP_DB.payments = [...INITIAL_EXCEL_PAYMENTS];
    }
    if (!Array.isArray(window.ERP_DB.trips)) {
        window.ERP_DB.trips = [];
    }
    if (!Array.isArray(window.ERP_DB.profiles)) {
        window.ERP_DB.profiles = [];
    }
    if (typeof saveLocalDatabase === "function") {
        saveLocalDatabase();
    }
}

// تحديث جميع القوائم والجداول في الصفحات
function refreshAllViews() {
    ensureInitialExcelDataLoaded();
    populateClientSelects();
    renderCalendarGrid();
    renderTripsTable();
    renderSelectedClientAccounting();
    renderMasterSummaryTable();
}

function populateClientSelects() {
    const tripSel = document.getElementById("tripClientSelect");
    const accSel = document.getElementById("accClientSelect");
    const currentAccVal = accSel ? accSel.value : "c1";
    const currentTripVal = tripSel ? tripSel.value : "c1";

    const optionsHtml = window.ERP_DB.clients.map(c =>
        `<option value="${c.id}">${c.name} (الفرد: ${c.rate})</option>`
    ).join("");

    if (tripSel) {
        tripSel.innerHTML = optionsHtml;
        if (currentTripVal) tripSel.value = currentTripVal;
    }
    if (accSel) {
        accSel.innerHTML = optionsHtml;
        if (currentAccVal && window.ERP_DB.clients.some(c => c.id === currentAccVal)) {
            accSel.value = currentAccVal;
        }
    }
}

// =========================================================================
// 1. محرك اقتراح أنسب ميعاد لحجز الروضة (Smart Rawdah Slot Recommender)
// =========================================================================
function suggestBestRawdahSlot() {
    const arrInput = document.getElementById("tripArrivalDate").value;
    const depInput = document.getElementById("tripDepartureDate").value;
    const badge = document.getElementById("suggestedStayBadge");
    const dateTxt = document.getElementById("suggestedDateText");
    const reasonTxt = document.getElementById("suggestedReasonText");
    const rawdahInput = document.getElementById("tripRawdahDate");

    if (!arrInput || !depInput) return;

    const arrDate = new Date(arrInput);
    const depDate = new Date(depInput);
    const diffDays = Math.round((depDate - arrDate) / (1000 * 60 * 60 * 24));

    if (diffDays < 0) {
        badge.textContent = "خطأ بالتاريخ";
        dateTxt.textContent = "تاريخ الخروج قبل تاريخ الدخول!";
        reasonTxt.textContent = "يرجى التأكد من إدخال فترة إقامة صحيحة في المدينة المنورة.";
        return;
    }

    badge.textContent = `إقامة ${diffDays + 1} أيام`;

    // توليد كل الأيام المتاحة في المدينة، مع تفضيل استبعاد يوم الوصول ويوم المغادرة إن أمكن
    let candidateDates = [];
    for (let i = 0; i <= diffDays; i++) {
        const d = new Date(arrDate);
        d.setDate(d.getDate() + i);
        const iso = d.toISOString().slice(0, 10);

        // حساب عدد المجموعات المسجلة في نفس اليوم لمعرفة الزحام
        const groupsOnDay = window.ERP_DB.trips.filter(t => t.rawdahDate === iso);
        const totalPilgrimsOnDay = groupsOnDay.reduce((sum, g) => sum + (Number(g.count) || 0), 0);

        // تقييم الأفضلية (نقاط أعلى لليوم الثاني والثالث، وخصم نقاط ليوم الوصول أو المغادرة أو الزحام)
        let score = 100;
        if (i === 0) score -= 50; // يوم الوصول مرهق وقد تتأخر الحافلات
        if (i === diffDays && diffDays > 0) score -= 40; // يوم المغادرة
        if (i === 1 || i === 2) score += 25; // اليوم الثاني أو الثالث هو المثالي
        score -= (groupsOnDay.length * 15); // تقليل التزاحم في نفس اليوم

        candidateDates.push({
            iso,
            dayIndex: i + 1,
            groupsCount: groupsOnDay.length,
            pilgrimsCount: totalPilgrimsOnDay,
            score
        });
    }

    candidateDates.sort((a, b) => b.score - a.score);
    const best = candidateDates[0];

    rawdahInput.value = best.iso;

    const formattedBest = new Date(best.iso).toLocaleDateString("ar-EG", {
        weekday: "long", year: "numeric", month: "long", day: "numeric"
    });

    dateTxt.textContent = `${formattedBest} (${best.iso})`;

    let reason = `اليوم رقم (${best.dayIndex}) من الإقامة بالمدينة بعيداً عن إرهاق الوصول وموعد المغادرة.`;
    if (best.groupsCount === 0) {
        reason += ` ✅ هذا اليوم متاح تماماً لديك في الجدول (لا توجد مجموعات أخرى).`;
    } else {
        reason += ` ⚠️ لديك ${best.groupsCount} مجموعة أخرى في هذا اليوم (${best.pilgrimsCount} معتمر).`;
    }
    reasonTxt.textContent = reason;
}

// =========================================================================
// 2. إضافة مجموعة للكليندر + رفع الملف لـ Google Drive + الترحيل للحسابات
// =========================================================================
async function addNewTrip() {
    const clientId = document.getElementById("tripClientSelect").value;
    const clientObj = window.ERP_DB.clients.find(c => c.id === clientId);
    const groupName = document.getElementById("tripGroupName").value.trim() || "مجموعة بدون اسم";
    const count = parseInt(document.getElementById("tripCount").value) || 0;
    const arrivalDate = document.getElementById("tripArrivalDate").value;
    const departureDate = document.getElementById("tripDepartureDate").value;
    const rawdahDate = document.getElementById("tripRawdahDate").value || arrivalDate;
    const status = document.getElementById("tripStatusSelect").value;
    const fileInput = document.getElementById("tripDriveFile");
    const autoAcc = document.getElementById("tripAutoAddAccounting").checked;

    if (!rawdahDate || count <= 0) {
        alert("يرجى تحديد العدد وتاريخ حجز الروضة أو فترة المدينة!");
        return;
    }

    const btn = document.getElementById("btnSaveTrip");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> جاري الحفظ والرفع للدرايف...`;

    let driveUrl = "";
    if (fileInput.files.length > 0 && clientObj) {
        driveUrl = await uploadFileToClientDrive(fileInput.files[0], clientObj.name) || "";
    }

    const newTrip = {
        id: "t_" + Date.now(),
        clientId,
        clientName: clientObj ? clientObj.name : "",
        groupName,
        count,
        arrivalDate,
        departureDate,
        rawdahDate,
        status,
        driveUrl
    };

    window.ERP_DB.trips.unshift(newTrip);

    // إضافة تلقائية في حساب العميل المالي بنفس تسعيرته
    if (autoAcc && clientObj) {
        const dParts = rawdahDate.split("-");
        const formattedD = dParts.length === 3 ? `${parseInt(dParts[2])}/${parseInt(dParts[1])}/${dParts[0]}` : rawdahDate;
        window.ERP_DB.rosters.push({
            id: "r_" + Date.now(),
            clientId: clientObj.id,
            date: formattedD,
            code: groupName,
            count: count,
            price: count * (clientObj.rate || 40),
            paidGreen: false,
            driveUrl: driveUrl
        });
    }

    await syncToCloud();
    refreshAllViews();

    document.getElementById("tripGroupName").value = "";
    fileInput.value = "";
    btn.disabled = false;
    btn.innerHTML = `<i class="fa-solid fa-calendar-plus"></i> حفظ المجموعة في الكليندر والدرايف`;
}

// =========================================================================
// 3. عرض الكليندر الشهري التفاعلي وجدول المجموعات والليبلز
// =========================================================================
function changeCalendarMonth(delta) {
    currentCalendarDate.setMonth(currentCalendarDate.getMonth() + delta);
    renderCalendarGrid();
}

function filterTripsByStatus(status) {
    activeTripStatusFilter = status;
    renderCalendarGrid();
    renderTripsTable();
}

function getStatusBadgeInfo(status) {
    const map = {
        registering: { text: "🔵 جاري التسجيل", cls: "status-registering" },
        registered:  { text: "🟡 تم التسجيل", cls: "status-registered" },
        booked:      { text: "🟢 تم الحجز", cls: "status-booked" },
        visited:     { text: "🟣 تمت الزيارة", cls: "status-visited" }
    };
    return map[status] || map.registering;
}

function renderCalendarGrid() {
    const grid = document.getElementById("calendarGrid");
    const title = document.getElementById("calendarMonthTitle");
    if (!grid || !title) return;

    const year = currentCalendarDate.getFullYear();
    const month = currentCalendarDate.getMonth();

    title.textContent = currentCalendarDate.toLocaleDateString("ar-EG", { month: "long", year: "numeric" });

    const firstDayIndex = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    let html = "";
    for (let i = 0; i < firstDayIndex; i++) {
        html += `<div class="min-h-[85px] rounded-xl bg-slate-900/30 border border-slate-800/40"></div>`;
    }

    for (let day = 1; day <= daysInMonth; day++) {
        const isoDate = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        const dayTrips = window.ERP_DB.trips.filter(t => {
            if (activeTripStatusFilter !== "all" && t.status !== activeTripStatusFilter) return false;
            return t.rawdahDate === isoDate;
        });

        const badgesHtml = dayTrips.map(t => {
            const info = getStatusBadgeInfo(t.status);
            return `<div class="mt-1 px-1.5 py-0.5 rounded text-[10px] font-bold truncate ${info.cls}" title="${t.clientName} - ${t.groupName} (${t.count})">
                ${t.groupName} (${t.count})
            </div>`;
        }).join("");

        const isToday = isoDate === new Date().toISOString().slice(0, 10);
        html += `
            <div class="min-h-[85px] p-1.5 rounded-xl bg-slate-900/80 border ${isToday ? 'border-amber-400' : 'border-slate-800'} hover:border-slate-600 transition flex flex-col">
                <div class="flex justify-between items-center">
                    <span class="text-xs font-extrabold ${isToday ? 'text-amber-400' : 'text-slate-400'}">${day}</span>
                    ${dayTrips.length ? `<span class="text-[9px] bg-slate-800 px-1.5 rounded text-amber-300">${dayTrips.length}</span>` : ''}
                </div>
                <div class="flex-1 overflow-y-auto max-h-[65px] space-y-0.5">${badgesHtml}</div>
            </div>
        `;
    }

    grid.innerHTML = html;
}

function renderTripsTable() {
    const tbody = document.getElementById("tripsTableBody");
    const countBadge = document.getElementById("tripsCountBadge");
    if (!tbody) return;

    const filtered = window.ERP_DB.trips.filter(t =>
        activeTripStatusFilter === "all" || t.status === activeTripStatusFilter
    );

    if (countBadge) countBadge.textContent = `${filtered.length} مجموعة`;

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="py-8 text-center text-slate-500">لا توجد مجموعات مسجلة في هذا التصنيف حالياً</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(t => {
        const info = getStatusBadgeInfo(t.status);
        return `
            <tr class="hover:bg-slate-800/40 transition">
                <td class="py-2.5 px-3 font-bold text-amber-300">${t.clientName}</td>
                <td class="py-2.5 px-3 font-bold text-white">${t.groupName}</td>
                <td class="py-2.5 px-3 font-mono font-bold text-emerald-400">${t.count}</td>
                <td class="py-2.5 px-3 text-[11px] text-slate-300" dir="ltr">${t.arrivalDate || '-'} ➔ ${t.departureDate || '-'}</td>
                <td class="py-2.5 px-3 font-mono font-bold text-amber-400" dir="ltr">${t.rawdahDate}</td>
                <td class="py-2.5 px-3">
                    <select onchange="updateTripStatus('${t.id}', this.value)" class="px-2 py-1 rounded-lg text-xs font-bold ${info.cls} bg-slate-900 focus:outline-none">
                        <option value="registering" ${t.status === 'registering' ? 'selected' : ''}>🔵 جاري التسجيل</option>
                        <option value="registered" ${t.status === 'registered' ? 'selected' : ''}>🟡 تم التسجيل</option>
                        <option value="booked" ${t.status === 'booked' ? 'selected' : ''}>🟢 تم الحجز</option>
                        <option value="visited" ${t.status === 'visited' ? 'selected' : ''}>🟣 تمت الزيارة</option>
                    </select>
                </td>
                <td class="py-2.5 px-3">
                    ${t.driveUrl ? `<a href="${t.driveUrl}" target="_blank" class="px-2.5 py-1 rounded-lg bg-blue-500/20 text-blue-300 hover:bg-blue-500 hover:text-white text-[11px] font-bold transition"><i class="fa-brands fa-google-drive ml-1"></i> فتح الملف</a>` : `<span class="text-slate-600">-</span>`}
                </td>
                <td class="py-2.5 px-3 text-center">
                    <button onclick="deleteTrip('${t.id}')" class="text-red-400 hover:text-red-300"><i class="fa-solid fa-trash"></i></button>
                </td>
            </tr>
        `;
    }).join("");
}

async function updateTripStatus(tripId, newStatus) {
    const trip = window.ERP_DB.trips.find(t => t.id === tripId);
    if (trip) {
        trip.status = newStatus;
        await syncToCloud();
        renderCalendarGrid();
        renderTripsTable();
    }
}

async function deleteTrip(tripId) {
    if (!confirm("هل تريد حذف هذه المجموعة من الكليندر؟")) return;
    window.ERP_DB.trips = window.ERP_DB.trips.filter(t => t.id !== tripId);
    await syncToCloud();
    renderCalendarGrid();
    renderTripsTable();
}

// =========================================================================
// 4. إدارة حسابات العملاء وكشوفات الحساب والـ Google Drive
// =========================================================================
function renderSelectedClientAccounting() {
    const sel = document.getElementById("accClientSelect");
    if (!sel) return;
    const clientId = sel.value;
    const client = window.ERP_DB.clients.find(c => c.id === clientId);
    if (!client) return;

    document.getElementById("accClientRate").value = client.rate;

    const rosters = window.ERP_DB.rosters.filter(r => r.clientId === clientId);
    const payments = window.ERP_DB.payments.filter(p => p.clientId === clientId);

    const totalCount = rosters.reduce((s, r) => s + (Number(r.count) || 0), 0);
    const totalAmount = rosters.reduce((s, r) => s + (Number(r.price) || 0), 0);
    const totalPaid = payments.reduce((s, p) => s + (Number(p.amount) || 0), 0);
    const remaining = totalAmount - totalPaid;

    document.getElementById("accTotalCount").textContent = totalCount.toLocaleString();
    document.getElementById("accTotalAmount").textContent = totalAmount.toLocaleString();
    document.getElementById("accTotalPaid").textContent = totalPaid.toLocaleString();
    document.getElementById("accRemaining").textContent = remaining.toLocaleString();

    // عرض جدول الكشوفات الخاصة بالعميل
    const rBody = document.getElementById("clientRostersTableBody");
    if (rosters.length === 0) {
        rBody.innerHTML = `<tr><td colspan="7" class="py-8 text-center text-slate-500">لا توجد كشوفات مسجلة لهذا العميل</td></tr>`;
    } else {
        rBody.innerHTML = rosters.map(r => `
            <tr class="${r.paidGreen ? 'row-paid-green' : 'hover:bg-slate-800/40'} transition">
                <td class="py-2.5 px-4 font-mono text-slate-200" dir="ltr">${r.date || '-'}</td>
                <td class="py-2.5 px-4 font-bold text-amber-300">${r.code || '-'}</td>
                <td class="py-2.5 px-4 font-mono font-bold text-white">${r.count}</td>
                <td class="py-2.5 px-4 font-mono font-bold text-emerald-400">${Number(r.price).toLocaleString()}</td>
                <td class="py-2.5 px-4">
                    ${r.driveUrl ? `<a href="${r.driveUrl}" target="_blank" class="px-2 py-1 rounded bg-blue-500/20 text-blue-300 text-[11px] font-bold"><i class="fa-brands fa-google-drive"></i> الدرايف</a>` : `<span class="text-slate-500">-</span>`}
                </td>
                <td class="py-2.5 px-4 text-center">
                    <button onclick="toggleRosterPaidGreen('${r.id}')" class="px-2 py-1 rounded-lg ${r.paidGreen ? 'bg-emerald-500 text-slate-950' : 'bg-slate-800 text-slate-400'} text-xs font-bold transition">
                        <i class="fa-solid fa-check"></i>
                    </button>
                </td>
                <td class="py-2.5 px-4 text-center">
                    <button onclick="deleteRosterEntry('${r.id}')" class="text-red-400 hover:text-red-300"><i class="fa-solid fa-trash"></i></button>
                </td>
            </tr>
        `).join("");
    }

    // عرض جدول الدفعات الخاصة بالعميل
    const pBody = document.getElementById("clientPaymentsTableBody");
    if (payments.length === 0) {
        pBody.innerHTML = `<tr><td colspan="4" class="py-6 text-center text-slate-500">لا توجد دفعات مسجلة</td></tr>`;
    } else {
        pBody.innerHTML = payments.map(p => `
            <tr class="hover:bg-slate-800/40 transition">
                <td class="py-2 px-4 font-mono text-slate-300" dir="ltr">${p.date}</td>
                <td class="py-2 px-4 font-mono font-bold text-emerald-400">${Number(p.amount).toLocaleString()}</td>
                <td class="py-2 px-4 text-slate-400">${p.note || '-'}</td>
                <td class="py-2 px-4 text-center">
                    <button onclick="deletePaymentEntry('${p.id}')" class="text-red-400 hover:text-red-300"><i class="fa-solid fa-trash"></i></button>
                </td>
            </tr>
        `).join("");
    }
}

function calcNewRosterPrice() {
    const cnt = parseInt(document.getElementById("newRosterCount").value) || 0;
    const rate = parseFloat(document.getElementById("accClientRate").value) || 40;
    document.getElementById("newRosterPrice").value = cnt * rate;
}

async function updateClientRate() {
    const clientId = document.getElementById("accClientSelect").value;
    const newRate = parseFloat(document.getElementById("accClientRate").value) || 40;
    const client = window.ERP_DB.clients.find(c => c.id === clientId);
    if (client) {
        client.rate = newRate;
        await syncToCloud();
        populateClientSelects();
    }
}

async function openNewClientModal() {
    const name = prompt("أدخل اسم العميل / مكتب السياحة الجديد:");
    if (!name || !name.trim()) return;
    const rateStr = prompt("أدخل سعر الفرد لهذا العميل (مثال: 40 أو 50):", "40");
    const rate = parseFloat(rateStr) || 40;
    const newId = "c_" + Date.now();
    window.ERP_DB.clients.push({ id: newId, name: name.trim(), rate });
    await syncToCloud();
    populateClientSelects();
    document.getElementById("accClientSelect").value = newId;
    renderSelectedClientAccounting();
}

async function addRosterAccountingEntry() {
    const clientId = document.getElementById("accClientSelect").value;
    const client = window.ERP_DB.clients.find(c => c.id === clientId);
    const rawDate = document.getElementById("newRosterDate").value;
    const count = parseInt(document.getElementById("newRosterCount").value) || 0;
    const code = document.getElementById("newRosterCode").value.trim();
    const price = parseInt(document.getElementById("newRosterPrice").value) || (count * (client?.rate || 40));
    const fileInput = document.getElementById("newRosterFile");

    if (count <= 0) {
        alert("يرجى إدخال العدد!");
        return;
    }

    const btn = document.getElementById("btnAddRosterEntry");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> جاري الحفظ...`;

    let driveUrl = "";
    if (fileInput.files.length > 0 && client) {
        driveUrl = await uploadFileToClientDrive(fileInput.files[0], client.name) || "";
    }

    let formattedDate = rawDate;
    if (rawDate && rawDate.includes("-")) {
        const parts = rawDate.split("-");
        formattedDate = `${parseInt(parts[2])}/${parseInt(parts[1])}/${parts[0]}`;
    }

    window.ERP_DB.rosters.push({
        id: "r_" + Date.now(),
        clientId,
        date: formattedDate || new Date().toLocaleDateString("en-GB"),
        code,
        count,
        price,
        paidGreen: false,
        driveUrl
    });

    await syncToCloud();
    renderSelectedClientAccounting();

    document.getElementById("newRosterCount").value = "";
    document.getElementById("newRosterCode").value = "";
    document.getElementById("newRosterPrice").value = "";
    fileInput.value = "";
    btn.disabled = false;
    btn.innerHTML = `<i class="fa-solid fa-check"></i> إدراج الكشف في الحساب`;
}

async function toggleRosterPaidGreen(rosterId) {
    const r = window.ERP_DB.rosters.find(x => x.id === rosterId);
    if (r) {
        r.paidGreen = !r.paidGreen;
        await syncToCloud();
        renderSelectedClientAccounting();
    }
}

async function deleteRosterEntry(rosterId) {
    if (!confirm("حذف هذا الكشف من حساب العميل؟")) return;
    window.ERP_DB.rosters = window.ERP_DB.rosters.filter(x => x.id !== rosterId);
    await syncToCloud();
    renderSelectedClientAccounting();
}

async function addClientPayment() {
    const clientId = document.getElementById("accClientSelect").value;
    const amount = parseInt(document.getElementById("newPaymentAmount").value) || 0;
    const rawDate = document.getElementById("newPaymentDate").value;
    const note = document.getElementById("newPaymentNote").value.trim() || "دفعة مسددة";

    if (amount <= 0) {
        alert("يرجى إدخال مبلغ الدفعة!");
        return;
    }

    let formattedDate = rawDate;
    if (rawDate && rawDate.includes("-")) {
        const parts = rawDate.split("-");
        formattedDate = `${parseInt(parts[2])}/${parseInt(parts[1])}/${parts[0]}`;
    }

    window.ERP_DB.payments.push({
        id: "p_" + Date.now(),
        clientId,
        date: formattedDate || new Date().toLocaleDateString("en-GB"),
        amount,
        note
    });

    await syncToCloud();
    renderSelectedClientAccounting();

    document.getElementById("newPaymentAmount").value = "";
    document.getElementById("newPaymentNote").value = "";
}

async function deletePaymentEntry(payId) {
    if (!confirm("حذف هذه الدفعة؟")) return;
    window.ERP_DB.payments = window.ERP_DB.payments.filter(x => x.id !== payId);
    await syncToCloud();
    renderSelectedClientAccounting();
}

// =========================================================================
// 5. تصدير كشف حساب عميل مفصل أو الشيت المجمع (جدول مجمل الفلوس) إلى Excel
// =========================================================================
function exportClientStatementExcel() {
    const clientId = document.getElementById("accClientSelect").value;
    const client = window.ERP_DB.clients.find(c => c.id === clientId);
    if (!client) return;

    const rosters = window.ERP_DB.rosters.filter(r => r.clientId === clientId);
    const payments = window.ERP_DB.payments.filter(p => p.clientId === clientId);

    const totalCount = rosters.reduce((s, r) => s + (Number(r.count) || 0), 0);
    const totalAmount = rosters.reduce((s, r) => s + (Number(r.price) || 0), 0);
    const totalPaid = payments.reduce((s, p) => s + (Number(p.amount) || 0), 0);
    const remaining = totalAmount - totalPaid;

    const rows = rosters.map((r, i) => ({
        "#": i + 1,
        "التاريخ": r.date,
        "الكود / البيان": r.code || "-",
        "العدد": r.count,
        "السعر": r.price,
        "حالة السداد": r.paidGreen ? "خالص (أخضر)" : "قيد الحساب"
    }));

    rows.push({});
    rows.push({ "#": "ملخص الحساب", "التاريخ": "إجمالي الأعداد", "الكود / البيان": totalCount, "العدد": "إجمالي الحساب", "السعر": totalAmount });
    rows.push({ "#": "السداد", "التاريخ": "إجمالي المسدد", "الكود / البيان": totalPaid, "العدد": "الباقي المستحق", "السعر": remaining });

    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, client.name.slice(0, 28));
    XLSX.writeFile(wb, `كشف_حساب_${client.name}_${new Date().toISOString().slice(0, 10)}.xlsx`);
}

function exportAllClientsMasterExcel() {
    const summaryRows = window.ERP_DB.clients.map(c => {
        const rosters = window.ERP_DB.rosters.filter(r => r.clientId === c.id);
        const payments = window.ERP_DB.payments.filter(p => p.clientId === c.id);
        const totalCount = rosters.reduce((s, r) => s + (Number(r.count) || 0), 0);
        const totalAmount = rosters.reduce((s, r) => s + (Number(r.price) || 0), 0);
        const totalPaid = payments.reduce((s, p) => s + (Number(p.amount) || 0), 0);
        return {
            "اسم الحساب": c.name,
            "سعر الفرد": c.rate,
            "إجمالي الأعداد": totalCount,
            "إجمالي الحساب": totalAmount,
            "إجمالي المدفوع": totalPaid,
            "الباقي المستحق": totalAmount - totalPaid
        };
    });

    const grandTotalAmount = summaryRows.reduce((s, r) => s + r["إجمالي الحساب"], 0);
    const grandTotalPaid = summaryRows.reduce((s, r) => s + r["إجمالي المدفوع"], 0);
    const grandRemaining = grandTotalAmount - grandTotalPaid;

    summaryRows.push({
        "اسم الحساب": "الإجمالي العام",
        "سعر الفرد": "-",
        "إجمالي الأعداد": summaryRows.reduce((s, r) => s + r["إجمالي الأعداد"], 0),
        "إجمالي الحساب": grandTotalAmount,
        "إجمالي المدفوع": grandTotalPaid,
        "الباقي المستحق": grandRemaining
    });

    const ws = XLSX.utils.json_to_sheet(summaryRows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "جدول مجمل الفلوس");
    XLSX.writeFile(wb, `مجمل_حسابات_الروضة_محمد_سامي_${new Date().toISOString().slice(0, 10)}.xlsx`);
}

function renderMasterSummaryTable() {
    // يتم تحديث الإجماليات تلقائياً
}

// =========================================================================
// ربط جميع الدوال صراحة بـ window لضمان عمل onclick في HTML بدون أي أخطاء
// =========================================================================
window.refreshAllViews = refreshAllViews;
window.ensureInitialExcelDataLoaded = ensureInitialExcelDataLoaded;
window.populateClientSelects = populateClientSelects;
window.suggestBestRawdahSlot = suggestBestRawdahSlot;
window.addNewTrip = addNewTrip;
window.changeCalendarMonth = changeCalendarMonth;
window.filterTripsByStatus = filterTripsByStatus;
window.getStatusBadgeInfo = getStatusBadgeInfo;
window.renderCalendarGrid = renderCalendarGrid;
window.renderTripsTable = renderTripsTable;
window.updateTripStatus = updateTripStatus;
window.deleteTrip = deleteTrip;
window.renderSelectedClientAccounting = renderSelectedClientAccounting;
window.calcNewRosterPrice = calcNewRosterPrice;
window.updateClientRate = updateClientRate;
window.openNewClientModal = openNewClientModal;
window.addRosterAccountingEntry = addRosterAccountingEntry;
window.toggleRosterPaidGreen = toggleRosterPaidGreen;
window.deleteRosterEntry = deleteRosterEntry;
window.addClientPayment = addClientPayment;
window.deletePaymentEntry = deletePaymentEntry;
window.exportClientStatementExcel = exportClientStatementExcel;
window.exportAllClientsMasterExcel = exportAllClientsMasterExcel;
window.renderMasterSummaryTable = renderMasterSummaryTable;

