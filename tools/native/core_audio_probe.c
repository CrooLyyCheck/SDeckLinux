/* Read-only x64 Core Audio ABI probe. No setters or input events. */
#define COBJMACROS
#include <windows.h>
#include <initguid.h>
#include <mmdeviceapi.h>
#include <endpointvolume.h>
#include <functiondiscoverykeys_devpkey.h>
#include <stdio.h>
#include <math.h>
#include "identity.h"

typedef struct {
    IAudioEndpointVolumeCallback iface;
    LONG refs, calls, invalid;
    HANDLE event;
} Callback;
static ULONG WINAPI callback_addref(IAudioEndpointVolumeCallback *iface)
{ return InterlockedIncrement(&((Callback *)iface)->refs); }
static ULONG WINAPI callback_release(IAudioEndpointVolumeCallback *iface)
{ return InterlockedDecrement(&((Callback *)iface)->refs); }
static HRESULT WINAPI callback_query(IAudioEndpointVolumeCallback *iface, REFIID iid, void **result)
{
    if (!result) return E_POINTER;
    *result=NULL;
    if (!IsEqualIID(iid,&IID_IUnknown) && !IsEqualIID(iid,&IID_IAudioEndpointVolumeCallback)) return E_NOINTERFACE;
    *result=iface; callback_addref(iface); return S_OK;
}
static HRESULT WINAPI callback_notify(IAudioEndpointVolumeCallback *iface, AUDIO_VOLUME_NOTIFICATION_DATA *data)
{
    Callback *callback=(Callback *)iface;
    if (!data || !data->nChannels || data->nChannels>64 || !isfinite(data->fMasterVolume)
            || data->fMasterVolume<0 || data->fMasterVolume>1)
        InterlockedIncrement(&callback->invalid);
    InterlockedIncrement(&callback->calls);
    if (callback->event) SetEvent(callback->event);
    return S_OK;
}
static IAudioEndpointVolumeCallbackVtbl callback_vtable={callback_query,callback_addref,callback_release,callback_notify};

int wmain(int argc, wchar_t **argv)
{
    IMMDeviceEnumerator *enumerator = NULL;
    IMMDeviceCollection *devices = NULL;
    HRESULT init, hr;
    UINT count = 0, readable = 0, muted = 0;
    UINT mapped = 0, default_aliases = 0;
    float minimum = 2.0f, maximum = -1.0f;
    FILE *output;
    HMODULE bridge = NULL;
    HRESULT (WINAPI *get_class)(REFCLSID, REFIID, void **) = NULL;
    HRESULT (WINAPI *can_unload)(void) = NULL;
    UINT identity_checks = 0;
    UINT callback_checks = 0;
    UINT property_checks=0, native_name_checks=0;
    UINT unavailable_checks=0, fallback_reads=0;
    BOOL unavailable_names_ok=TRUE;
    Callback callback={{&callback_vtable},1,0,0,NULL};
    BOOL lifetime_ok = TRUE;
    BOOL wait_notify=FALSE, notification_observed=FALSE, registered=FALSE, friendly_names=FALSE;
    if (argc < 2 || argc > 5) return 2;
    for (int i=3; i<argc; ++i) {
        if (!wcscmp(argv[i],L"--wait-notify") && !wait_notify) wait_notify=TRUE;
        else if (!wcscmp(argv[i],L"--registered") && !registered) registered=TRUE;
        else if (!wcscmp(argv[i],L"--friendly-names") && !friendly_names) friendly_names=TRUE;
        else return 2;
    }
    if (wait_notify) {
        callback.event=CreateEventW(NULL,TRUE,FALSE,NULL);
        if (!callback.event) return 6;
    }
    if (argc >= 3) {
        bridge = LoadLibraryW(argv[2]);
        if (!bridge) return 4;
        get_class = (HRESULT (WINAPI *)(REFCLSID, REFIID, void **))
                (void *)GetProcAddress(bridge, "DllGetClassObject");
        can_unload = (HRESULT (WINAPI *)(void))(void *)GetProcAddress(bridge, "DllCanUnloadNow");
        if (!get_class || !can_unload) { FreeLibrary(bridge); return 5; }
    }
    init = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    if (FAILED(init)) return 3;
    if (get_class && !registered) {
        IClassFactory *factory = NULL;
        hr = get_class(&CLSID_MMDeviceEnumerator, &IID_IClassFactory, (void **)&factory);
        if (SUCCEEDED(hr)) {
            hr = IClassFactory_CreateInstance(factory, NULL, &IID_IMMDeviceEnumerator, (void **)&enumerator);
            IClassFactory_Release(factory);
        }
        lifetime_ok = SUCCEEDED(hr) && can_unload() == S_FALSE;
    } else {
        hr = CoCreateInstance(&CLSID_MMDeviceEnumerator, NULL, CLSCTX_INPROC_SERVER,
                &IID_IMMDeviceEnumerator, (void **)&enumerator);
        if (registered) lifetime_ok=SUCCEEDED(hr) && can_unload()==S_FALSE;
    }
    if (SUCCEEDED(hr))
        hr = IMMDeviceEnumerator_EnumAudioEndpoints(enumerator, eAll, DEVICE_STATE_ACTIVE, &devices);
    if (SUCCEEDED(hr)) hr = IMMDeviceCollection_GetCount(devices, &count);
    for (UINT i = 0; SUCCEEDED(hr) && i < count; ++i) {
        IMMDevice *device = NULL;
        IAudioEndpointVolume *volume = NULL;
        HRESULT item_hr = IMMDeviceCollection_Item(devices, i, &device);
        if (SUCCEEDED(item_hr) && bridge) {
            IMMEndpoint *endpoint = NULL;
            IUnknown *identity = NULL;
            HRESULT identity_hr = IMMDevice_QueryInterface(device, &IID_IMMEndpoint, (void **)&endpoint);
            if (SUCCEEDED(identity_hr)) {
                identity_hr = IMMEndpoint_QueryInterface(endpoint, &IID_IUnknown, (void **)&identity);
                if (SUCCEEDED(identity_hr) && identity == (IUnknown *)device) ++identity_checks;
            }
            if (identity) IUnknown_Release(identity);
            if (endpoint) IMMEndpoint_Release(endpoint);
        }
        if (SUCCEEDED(item_hr)) {
            DBEndpointIdentity identity;
            if (SUCCEEDED(db_endpoint_identity(device, &identity))) {
                ++mapped;
                if (identity.follows_default) ++default_aliases;
                if (friendly_names) {
                    IPropertyStore *store=NULL;
                    PROPVARIANT name,other;
                    IUnknown *store_identity=NULL;
                    DWORD total=0;
                    PROPERTYKEY first;
                    ZeroMemory(&name,sizeof(name));ZeroMemory(&other,sizeof(other));
                    HRESULT property_hr=IMMDevice_OpenPropertyStore(device,STGM_READ,&store);
                    if (SUCCEEDED(property_hr)) property_hr=IPropertyStore_QueryInterface(store,&IID_IUnknown,(void **)&store_identity);
                    if (SUCCEEDED(property_hr) && store_identity!=(IUnknown *)store) property_hr=E_FAIL;
                    if (SUCCEEDED(property_hr)) property_hr=IPropertyStore_GetCount(store,&total);
                    if (SUCCEEDED(property_hr) && !total) property_hr=E_FAIL;
                    if (SUCCEEDED(property_hr)) property_hr=IPropertyStore_GetAt(store,0,&first);
                    if (SUCCEEDED(property_hr)) property_hr=IPropertyStore_GetValue(store,&PKEY_Device_FriendlyName,&name);
                    if (SUCCEEDED(property_hr)) property_hr=IPropertyStore_GetValue(store,&PKEY_DeviceInterface_FriendlyName,&other);
                    if (SUCCEEDED(property_hr) && name.vt==VT_LPWSTR && name.pwszVal && name.pwszVal[0]
                            && other.vt==VT_LPWSTR && other.pwszVal && other.pwszVal[0]) {
                        ++property_checks;
                        if (!identity.follows_default && !wcsncmp(name.pwszVal,L"Native display: ",16)
                                && !wcscmp(name.pwszVal+16,identity.name)) ++native_name_checks;
                    }
                    PropVariantClear(&name);PropVariantClear(&other);
                    if (store_identity) IUnknown_Release(store_identity);
                    if (store) IPropertyStore_Release(store);
                }
            }
        }
        if (SUCCEEDED(item_hr)) item_hr = IMMDevice_Activate(device, &IID_IAudioEndpointVolume,
                        CLSCTX_INPROC_SERVER, NULL, (void **)&volume);
        if (SUCCEEDED(item_hr)) {
            float scalar = 0;
            BOOL mute = FALSE;
            item_hr = IAudioEndpointVolume_GetMasterVolumeLevelScalar(volume, &scalar);
            if (SUCCEEDED(item_hr)) item_hr = IAudioEndpointVolume_GetMute(volume, &mute);
            if (SUCCEEDED(item_hr)) {
                ++readable;
                if (mute) ++muted;
                if (scalar < minimum) minimum = scalar;
                if (scalar > maximum) maximum = scalar;
            }
            if (bridge && SUCCEEDED(item_hr)) {
                HRESULT notify_hr=IAudioEndpointVolume_RegisterControlChangeNotify(volume,&callback.iface);
                if (SUCCEEDED(notify_hr)) {
                    if (wait_notify && !i) {
                        FILE *ready=_wfopen(argv[1],L"wb");
                        if (ready) { fputs("{\"stage\":\"callback-ready\"}",ready); fclose(ready); }
                        notification_observed=WaitForSingleObject(callback.event,5000)==WAIT_OBJECT_0;
                    }
                    HRESULT duplicate=IAudioEndpointVolume_RegisterControlChangeNotify(volume,&callback.iface);
                    HRESULT removed=IAudioEndpointVolume_UnregisterControlChangeNotify(volume,&callback.iface);
                    HRESULT missing=IAudioEndpointVolume_UnregisterControlChangeNotify(volume,&callback.iface);
                    if (duplicate==E_INVALIDARG && SUCCEEDED(removed) && missing==E_INVALIDARG) ++callback_checks;
                }
            }
        }
        if (volume) IAudioEndpointVolume_Release(volume);
        if (device) IMMDevice_Release(device);
    }
    if (devices) IMMDeviceCollection_Release(devices);
    devices=NULL;
    if (friendly_names && enumerator) {
        UINT unavailable=0;
        HRESULT fallback_hr=IMMDeviceEnumerator_EnumAudioEndpoints(enumerator,eAll,DEVICE_STATE_NOTPRESENT,&devices);
        if (SUCCEEDED(fallback_hr)) fallback_hr=IMMDeviceCollection_GetCount(devices,&unavailable);
        if (unavailable>256) fallback_hr=E_FAIL;
        for (UINT i=0;SUCCEEDED(fallback_hr) && i<unavailable;++i) {
            IMMDevice *device=NULL;
            IPropertyStore *store=NULL;
            PROPVARIANT name;
            DBEndpointIdentity identity;
            ZeroMemory(&name,sizeof(name));
            fallback_hr=IMMDeviceCollection_Item(devices,i,&device);
            if (SUCCEEDED(fallback_hr) && SUCCEEDED(db_endpoint_identity(device,&identity)) && !identity.follows_default) ++fallback_reads;
            if (SUCCEEDED(fallback_hr)) fallback_hr=IMMDevice_OpenPropertyStore(device,STGM_READ,&store);
            if (SUCCEEDED(fallback_hr)) fallback_hr=IPropertyStore_GetValue(store,&PKEY_Device_FriendlyName,&name);
            if (SUCCEEDED(fallback_hr) && name.vt==VT_LPWSTR && name.pwszVal
                    && !wcsstr(name.pwszVal,L"Speakers (Speakers (")
                    && !wcsstr(name.pwszVal,L"Microphone (Microphone (")) ++unavailable_checks;
            else unavailable_names_ok=FALSE;
            PropVariantClear(&name);
            if (store) IPropertyStore_Release(store);
            if (device) IMMDevice_Release(device);
        }
        if (FAILED(fallback_hr)) unavailable_names_ok=FALSE;
        if (devices) IMMDeviceCollection_Release(devices);
    }
    if (enumerator) IMMDeviceEnumerator_Release(enumerator);
    if (can_unload) {
        ULONGLONG deadline=GetTickCount64()+5000;
        while (can_unload()!=S_OK && GetTickCount64()<deadline) Sleep(20);
        lifetime_ok = lifetime_ok && can_unload()==S_OK && callback.refs==1;
    }
    output = _wfopen(argv[1], L"wb");
    if (output) {
        fprintf(output, "{\"version\":1,\"hresult\":%lu,\"devices\":%u,"
                "\"readable\":%u,\"muted\":%u,\"minimum\":%.8f,\"maximum\":%.8f,"
                "\"mapped\":%u,\"default_aliases\":%u,\"identity_checks\":%u,"
                "\"lifetime_ok\":%s,\"callback_checks\":%u,\"callback_data_valid\":%s,"
                "\"notification_observed\":%s,\"property_checks\":%u,\"native_name_checks\":%u,"
                "\"unavailable_checks\":%u,\"fallback_reads\":%u,\"unavailable_names_ok\":%s,\"setters_called\":0}\n",
                (unsigned long)hr, count, readable, muted,
                readable ? minimum : 0.0f, readable ? maximum : 0.0f, mapped, default_aliases,
                identity_checks, lifetime_ok ? "true" : "false", callback_checks,
                callback.invalid ? "false" : "true", notification_observed ? "true" : "false",
                property_checks,native_name_checks,unavailable_checks,fallback_reads,unavailable_names_ok?"true":"false");
        fclose(output);
    }
    CoUninitialize();
    if (bridge) FreeLibrary(bridge);
    if (callback.event) CloseHandle(callback.event);
    return !output || FAILED(hr) || readable != count || mapped != count || !lifetime_ok
            || (bridge && (identity_checks != count || callback_checks != count || callback.invalid))
            || (friendly_names && (property_checks!=count || native_name_checks!=count-default_aliases || !unavailable_names_ok))
            || (wait_notify && !notification_observed);
}
