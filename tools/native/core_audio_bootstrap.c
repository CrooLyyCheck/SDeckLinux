/* Probe-only Node-API initializer: activate a thread-local COM manifest.
 * No Node internals, plugin patches or persistent COM registration are used.
 * Node-API v1 registration ABI uses two opaque pointer arguments.
 */
#include <windows.h>
#include <wchar.h>

__declspec(dllexport) void *napi_register_module_v1(void *env, void *exports)
{
    HMODULE module;
    WCHAR path[32768], *suffix;
    ACTCTXW context;
    HANDLE handle;
    ULONG_PTR cookie;
    DWORD length;
    (void)env;
    SetEnvironmentVariableW(L"DECKBRIDGE_CORE_AUDIO_ACTIVE", L"0");
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            (LPCWSTR)(void *)&napi_register_module_v1, &module)) return exports;
    length = GetModuleFileNameW(module, path, 32768);
    if (!length || length >= 32750) return exports;
    suffix = wcsrchr(path, L'.');
    if (!suffix) return exports;
    wcscpy(suffix, L".manifest");
    ZeroMemory(&context, sizeof(context));
    context.cbSize = sizeof(context);
    context.lpSource = path;
    handle = CreateActCtxW(&context);
    if (handle == INVALID_HANDLE_VALUE) return exports;
    if (!ActivateActCtx(handle, &cookie)) { ReleaseActCtx(handle); return exports; }
    /* The probe process owns this activation until exit. No other process changes. */
    SetEnvironmentVariableW(L"DECKBRIDGE_CORE_AUDIO_ACTIVE", L"1");
    return exports;
}
