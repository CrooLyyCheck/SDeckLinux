#define COBJMACROS
#include "identity.h"
#include <wchar.h>
#include <string.h>

HRESULT db_endpoint_identity(IMMDevice *device, DBEndpointIdentity *identity)
{
    LPWSTR id = NULL;
    GUID wanted;
    HKEY registry = NULL;
    HRESULT hr;
    WCHAR *guid_start;
    if (!device || !identity) return E_POINTER;
    ZeroMemory(identity, sizeof(*identity));
    hr = IMMDevice_GetId(device, &id);
    if (FAILED(hr)) return hr;
    guid_start = wcsrchr(id, L'{');
    hr = guid_start ? CLSIDFromString(guid_start, &wanted) : E_INVALIDARG;
    CoTaskMemFree(id);
    if (FAILED(hr)) return hr;
    if (RegOpenKeyExW(HKEY_CURRENT_USER,
            L"Software\\Wine\\Drivers\\winepulse.drv\\devices", 0,
            KEY_READ | KEY_WOW64_64KEY, &registry) != ERROR_SUCCESS)
        return HRESULT_FROM_WIN32(ERROR_NOT_FOUND);
    hr = HRESULT_FROM_WIN32(ERROR_NOT_FOUND);
    for (DWORD index = 0; index < 256; ++index) {
        WCHAR key[4098];
        DWORD length = 4098, bytes = sizeof(GUID), type = 0;
        GUID candidate;
        LSTATUS status = RegEnumKeyExW(registry, index, key, &length, NULL, NULL, NULL, NULL);
        if (status == ERROR_NO_MORE_ITEMS) break;
        if (status != ERROR_SUCCESS) {
            hr = HRESULT_FROM_WIN32(status);
            break;
        }
        if (length < 2 || key[1] != L',' || (key[0] != L'0' && key[0] != L'1')) continue;
        status = RegGetValueW(registry, key, L"guid", RRF_RT_REG_BINARY,
                &type, &candidate, &bytes);
        if (status != ERROR_SUCCESS || bytes != sizeof(GUID)) continue;
        if (!IsEqualGUID(&candidate, &wanted)) continue;
        identity->flow = key[0] == L'0' ? eRender : eCapture;
        memcpy(identity->name, key + 2, (length - 2 + 1) * sizeof(WCHAR));
        identity->follows_default = !identity->name[0];
        hr = S_OK;
        break;
    }
    RegCloseKey(registry);
    return hr;
}
