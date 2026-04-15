module.exports = [
"[project]/lib/supabase.ts [app-rsc] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "supabase",
    ()=>supabase
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f40$supabase$2f$supabase$2d$js$2f$dist$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i("[project]/node_modules/@supabase/supabase-js/dist/index.mjs [app-rsc] (ecmascript) <locals>");
;
let _client = null;
function getClient() {
    if (_client) return _client;
    const url = ("TURBOPACK compile-time value", "https://wymphxeancscjoseazlk.supabase.co");
    const key = ("TURBOPACK compile-time value", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind5bXBoeGVhbmNzY2pvc2VhemxrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ5NDgxNjEsImV4cCI6MjA5MDUyNDE2MX0.BI4_6OenxwsjF9XOJQUm-QkXMev1i2Zt7FqYosi-QQw");
    if ("TURBOPACK compile-time falsy", 0) //TURBOPACK unreachable
    ;
    _client = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f40$supabase$2f$supabase$2d$js$2f$dist$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__$3c$locals$3e$__["createClient"])(url, key);
    return _client;
}
const supabase = new Proxy({}, {
    get (_target, prop) {
        return getClient()[prop];
    }
});
}),
];

//# sourceMappingURL=lib_supabase_ts_5232f976._.js.map