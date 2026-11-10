/* Preserve Wine enumeration/properties; replace only endpoint-volume activation. */
#define COBJMACROS
#include <windows.h>
#include <initguid.h>
#include "client.h"
#include <endpointvolume.h>

static LONG objects, locks;
void db_object_created(void) { InterlockedIncrement(&objects); }
void db_object_destroyed(void) { InterlockedDecrement(&objects); }

typedef struct { IMMDeviceEnumerator iface; LONG refs; IMMDeviceEnumerator *real; HMODULE module; } Enumerator;
typedef struct { IMMDeviceCollection iface; LONG refs; IMMDeviceCollection *real; HMODULE module; } Collection;
typedef struct { IMMDevice iface; IMMEndpoint endpoint; LONG refs; IMMDevice *real; HMODULE module; } Device;
typedef struct { IClassFactory iface; LONG refs; } Factory;

static HRESULT wrap_device(IMMDevice *real, IMMDevice **result);
static HRESULT wrap_collection(IMMDeviceCollection *real, IMMDeviceCollection **result);
static HRESULT wrap_enumerator(IMMDeviceEnumerator *real, IMMDeviceEnumerator **result);

static HMODULE retain_wine(void)
{
    return LoadLibraryExW(L"mmdevapi.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
}

#define DEFINE_REFS(tag, Type, Interface) \
static ULONG WINAPI tag##_addref(Interface *iface) { return InterlockedIncrement(&((Type *)iface)->refs); } \
static ULONG WINAPI tag##_release(Interface *iface) { \
    Type *p=(Type *)iface; ULONG n=InterlockedDecrement(&p->refs); \
    if (!n) { Interface##_Release(p->real); FreeLibrary(p->module); CoTaskMemFree(p); db_object_destroyed(); } return n; }

DEFINE_REFS(enumerator, Enumerator, IMMDeviceEnumerator)
DEFINE_REFS(collection, Collection, IMMDeviceCollection)
DEFINE_REFS(device, Device, IMMDevice)

static HRESULT WINAPI enumerator_query(IMMDeviceEnumerator *iface, REFIID iid, void **result)
{
    if (!result) return E_POINTER;
    *result=NULL;
    if (!IsEqualIID(iid,&IID_IUnknown) && !IsEqualIID(iid,&IID_IMMDeviceEnumerator)) return E_NOINTERFACE;
    *result=iface; enumerator_addref(iface); return S_OK;
}
static HRESULT WINAPI collection_query(IMMDeviceCollection *iface, REFIID iid, void **result)
{
    if (!result) return E_POINTER;
    *result=NULL;
    if (!IsEqualIID(iid,&IID_IUnknown) && !IsEqualIID(iid,&IID_IMMDeviceCollection)) return E_NOINTERFACE;
    *result=iface; collection_addref(iface); return S_OK;
}
static HRESULT WINAPI device_query(IMMDevice *iface, REFIID iid, void **result)
{
    Device *p=(Device *)iface;
    if (!result) return E_POINTER;
    *result=NULL;
    if (IsEqualIID(iid,&IID_IMMEndpoint)) {
        IMMEndpoint *native=NULL;
        HRESULT hr=IMMDevice_QueryInterface(p->real,&IID_IMMEndpoint,(void **)&native);
        if (FAILED(hr)) return hr;
        IMMEndpoint_Release(native);
        *result=&p->endpoint;
    } else if (IsEqualIID(iid,&IID_IUnknown) || IsEqualIID(iid,&IID_IMMDevice)) *result=iface;
    else return E_NOINTERFACE;
    device_addref(iface); return S_OK;
}
static Device *endpoint_owner(IMMEndpoint *iface) { return CONTAINING_RECORD(iface,Device,endpoint); }
static HRESULT WINAPI endpoint_query(IMMEndpoint *iface, REFIID iid, void **result)
{ return device_query(&endpoint_owner(iface)->iface,iid,result); }
static ULONG WINAPI endpoint_addref(IMMEndpoint *iface)
{ return device_addref(&endpoint_owner(iface)->iface); }
static ULONG WINAPI endpoint_release(IMMEndpoint *iface)
{ return device_release(&endpoint_owner(iface)->iface); }
static HRESULT WINAPI endpoint_flow(IMMEndpoint *iface, EDataFlow *flow)
{
    IMMEndpoint *native=NULL;
    HRESULT hr;
    if (!flow) return E_POINTER;
    hr=IMMDevice_QueryInterface(endpoint_owner(iface)->real,&IID_IMMEndpoint,(void **)&native);
    if (SUCCEEDED(hr)) { hr=IMMEndpoint_GetDataFlow(native,flow); IMMEndpoint_Release(native); }
    return hr;
}

static HRESULT WINAPI enumerator_enum(IMMDeviceEnumerator *iface, EDataFlow flow, DWORD state, IMMDeviceCollection **result)
{
    IMMDeviceCollection *native=NULL;
    HRESULT hr;
    if (!result) return E_POINTER;
    *result=NULL;
    hr=IMMDeviceEnumerator_EnumAudioEndpoints(((Enumerator *)iface)->real,flow,state,&native);
    if (SUCCEEDED(hr)) { hr=wrap_collection(native,result); IMMDeviceCollection_Release(native); }
    return hr;
}
static HRESULT WINAPI enumerator_default(IMMDeviceEnumerator *iface, EDataFlow flow, ERole role, IMMDevice **result)
{
    IMMDevice *native=NULL;
    HRESULT hr;
    if (!result) return E_POINTER;
    *result=NULL;
    hr=IMMDeviceEnumerator_GetDefaultAudioEndpoint(((Enumerator *)iface)->real,flow,role,&native);
    if (SUCCEEDED(hr)) { hr=wrap_device(native,result); IMMDevice_Release(native); }
    return hr;
}
static HRESULT WINAPI enumerator_get(IMMDeviceEnumerator *iface, LPCWSTR id, IMMDevice **result)
{
    IMMDevice *native=NULL;
    HRESULT hr;
    if (!result) return E_POINTER;
    *result=NULL;
    hr=IMMDeviceEnumerator_GetDevice(((Enumerator *)iface)->real,id,&native);
    if (SUCCEEDED(hr)) { hr=wrap_device(native,result); IMMDevice_Release(native); }
    return hr;
}
static HRESULT WINAPI enumerator_register(IMMDeviceEnumerator *iface, IMMNotificationClient *client)
{ return IMMDeviceEnumerator_RegisterEndpointNotificationCallback(((Enumerator *)iface)->real,client); }
static HRESULT WINAPI enumerator_unregister(IMMDeviceEnumerator *iface, IMMNotificationClient *client)
{ return IMMDeviceEnumerator_UnregisterEndpointNotificationCallback(((Enumerator *)iface)->real,client); }
static HRESULT WINAPI collection_count(IMMDeviceCollection *iface, UINT *count)
{ return IMMDeviceCollection_GetCount(((Collection *)iface)->real,count); }
static HRESULT WINAPI collection_item(IMMDeviceCollection *iface, UINT index, IMMDevice **result)
{
    IMMDevice *native=NULL;
    HRESULT hr;
    if (!result) return E_POINTER;
    *result=NULL;
    hr=IMMDeviceCollection_Item(((Collection *)iface)->real,index,&native);
    if (SUCCEEDED(hr)) { hr=wrap_device(native,result); IMMDevice_Release(native); }
    return hr;
}
static HRESULT WINAPI device_activate(IMMDevice *iface, REFIID iid, DWORD context, PROPVARIANT *params, void **result)
{
    Device *p=(Device *)iface;
    if (!result) return E_POINTER;
    *result=NULL;
    if (IsEqualIID(iid,&IID_IAudioEndpointVolume) || IsEqualIID(iid,&IID_IAudioEndpointVolumeEx)) {
        if (!(context & CLSCTX_INPROC_SERVER) || params) return E_INVALIDARG;
        return db_volume_create(p->real,iid,result);
    }
    return IMMDevice_Activate(p->real,iid,context,params,result);
}
static HRESULT WINAPI device_store(IMMDevice *iface, DWORD mode, IPropertyStore **store)
{ return IMMDevice_OpenPropertyStore(((Device *)iface)->real,mode,store); }
static HRESULT WINAPI device_id(IMMDevice *iface, LPWSTR *id)
{ return IMMDevice_GetId(((Device *)iface)->real,id); }
static HRESULT WINAPI device_state(IMMDevice *iface, DWORD *state)
{ return IMMDevice_GetState(((Device *)iface)->real,state); }

static IMMDeviceEnumeratorVtbl enumerator_vtable={enumerator_query,enumerator_addref,enumerator_release,
    enumerator_enum,enumerator_default,enumerator_get,enumerator_register,enumerator_unregister};
static IMMDeviceCollectionVtbl collection_vtable={collection_query,collection_addref,collection_release,
    collection_count,collection_item};
static IMMDeviceVtbl device_vtable={device_query,device_addref,device_release,device_activate,
    device_store,device_id,device_state};
static IMMEndpointVtbl endpoint_vtable={endpoint_query,endpoint_addref,endpoint_release,endpoint_flow};

#define WRAP_BODY(Type, Interface, table) \
    Type *p=CoTaskMemAlloc(sizeof(*p)); \
    if (!p) return E_OUTOFMEMORY; \
    p->module=retain_wine(); \
    if (!p->module) { CoTaskMemFree(p); return E_FAIL; } \
    p->iface.lpVtbl=&table; p->refs=1; p->real=real; Interface##_AddRef(real); db_object_created();

static HRESULT wrap_enumerator(IMMDeviceEnumerator *real, IMMDeviceEnumerator **result)
{ WRAP_BODY(Enumerator,IMMDeviceEnumerator,enumerator_vtable) *result=&p->iface; return S_OK; }
static HRESULT wrap_collection(IMMDeviceCollection *real, IMMDeviceCollection **result)
{ WRAP_BODY(Collection,IMMDeviceCollection,collection_vtable) *result=&p->iface; return S_OK; }
static HRESULT wrap_device(IMMDevice *real, IMMDevice **result)
{ WRAP_BODY(Device,IMMDevice,device_vtable) p->endpoint.lpVtbl=&endpoint_vtable; *result=&p->iface; return S_OK; }

static ULONG WINAPI factory_addref(IClassFactory *iface)
{ return InterlockedIncrement(&((Factory *)iface)->refs); }
static ULONG WINAPI factory_release(IClassFactory *iface)
{
    Factory *p=(Factory *)iface;
    ULONG n=InterlockedDecrement(&p->refs);
    if (!n) { CoTaskMemFree(p); db_object_destroyed(); }
    return n;
}
static HRESULT WINAPI factory_query(IClassFactory *iface, REFIID iid, void **result)
{
    if (!result) return E_POINTER;
    *result=NULL;
    if (!IsEqualIID(iid,&IID_IUnknown) && !IsEqualIID(iid,&IID_IClassFactory)) return E_NOINTERFACE;
    *result=iface; factory_addref(iface); return S_OK;
}
static HRESULT WINAPI factory_create(IClassFactory *iface, IUnknown *outer, REFIID iid, void **result)
{
    HMODULE module;
    HRESULT (WINAPI *get_class)(REFCLSID,REFIID,void **);
    IClassFactory *factory=NULL;
    IMMDeviceEnumerator *native=NULL, *wrapped=NULL;
    HRESULT hr=E_FAIL;
    (void)iface;
    if (!result) return E_POINTER;
    *result=NULL;
    if (outer) return CLASS_E_NOAGGREGATION;
    module=retain_wine();
    if (!module) return hr;
    get_class=(HRESULT (WINAPI *)(REFCLSID,REFIID,void **))(void *)GetProcAddress(module,"DllGetClassObject");
    if (get_class) hr=get_class(&CLSID_MMDeviceEnumerator,&IID_IClassFactory,(void **)&factory);
    if (SUCCEEDED(hr)) hr=IClassFactory_CreateInstance(factory,NULL,&IID_IMMDeviceEnumerator,(void **)&native);
    if (SUCCEEDED(hr)) hr=wrap_enumerator(native,&wrapped);
    if (SUCCEEDED(hr)) hr=IMMDeviceEnumerator_QueryInterface(wrapped,iid,result);
    if (wrapped) IMMDeviceEnumerator_Release(wrapped);
    if (native) IMMDeviceEnumerator_Release(native);
    if (factory) IClassFactory_Release(factory);
    FreeLibrary(module);
    return hr;
}
static HRESULT WINAPI factory_lock(IClassFactory *iface, BOOL lock)
{
    (void)iface;
    if (lock) InterlockedIncrement(&locks);
    else {
        LONG n;
        do { n=InterlockedCompareExchange(&locks,0,0); if (n<=0) return E_UNEXPECTED; }
        while (InterlockedCompareExchange(&locks,n-1,n)!=n);
    }
    return S_OK;
}
static IClassFactoryVtbl factory_vtable={factory_query,factory_addref,factory_release,factory_create,factory_lock};

HRESULT WINAPI DllGetClassObject(REFCLSID clsid, REFIID iid, void **result)
{
    Factory *factory;
    HRESULT hr;
    if (!result) return E_POINTER;
    *result=NULL;
    if (!IsEqualCLSID(clsid,&CLSID_MMDeviceEnumerator)) return CLASS_E_CLASSNOTAVAILABLE;
    factory=CoTaskMemAlloc(sizeof(*factory));
    if (!factory) return E_OUTOFMEMORY;
    factory->iface.lpVtbl=&factory_vtable; factory->refs=1; db_object_created();
    hr=factory_query(&factory->iface,iid,result);
    factory_release(&factory->iface);
    return hr;
}
HRESULT WINAPI DllCanUnloadNow(void)
{ return InterlockedCompareExchange(&objects,0,0) || InterlockedCompareExchange(&locks,0,0) ? S_FALSE : S_OK; }
