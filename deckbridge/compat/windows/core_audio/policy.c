/* Shared Windows policy boundary; no plugin protocol or registry writes. */
#define COBJMACROS
#include "policy.h"

const CLSID DB_CLSID_PolicyVista={0x294935ce,0xf637,0x4e7c,{0xa4,0x1b,0xab,0x25,0x54,0x60,0xb8,0x62}};
const IID DB_IID_PolicyVista={0x568b9108,0x44bf,0x40b4,{0x90,0x06,0x86,0xaf,0xe5,0xb5,0xa6,0x20}};
typedef struct { DBPolicyVista iface; LONG refs; } Policy;

static ULONG WINAPI addref(DBPolicyVista *iface)
{ return InterlockedIncrement(&((Policy *)iface)->refs); }
static ULONG WINAPI release(DBPolicyVista *iface)
{
    Policy *p=(Policy *)iface;
    ULONG n=InterlockedDecrement(&p->refs);
    if (!n) { CoTaskMemFree(p); db_object_destroyed(); }
    return n;
}
static HRESULT WINAPI query(DBPolicyVista *iface,REFIID iid,void **out)
{
    if (!out) return E_POINTER;
    *out=NULL;
    if (!IsEqualIID(iid,&IID_IUnknown) && !IsEqualIID(iid,&DB_IID_PolicyVista)) return E_NOINTERFACE;
    *out=iface; addref(iface); return S_OK;
}
static HRESULT WINAPI set_default(DBPolicyVista *iface,LPCWSTR id,ERole role)
{
    IMMDeviceEnumerator *enumerator=NULL;
    IMMDevice *device=NULL;
    HMODULE module=NULL;
    DBEndpointIdentity identity;
    DBReply reply;
    HRESULT hr;
    DWORD state=0;
    (void)iface;
    if (!id) return E_POINTER;
    if (role!=eConsole && role!=eMultimedia && role!=eCommunications) return E_INVALIDARG;
    if (role==eCommunications) return E_NOTIMPL;
    hr=db_wine_enumerator(&enumerator,&module);
    if (SUCCEEDED(hr)) hr=IMMDeviceEnumerator_GetDevice(enumerator,id,&device);
    if (SUCCEEDED(hr)) hr=IMMDevice_GetState(device,&state);
    if (SUCCEEDED(hr) && state!=DEVICE_STATE_ACTIVE) hr=HRESULT_FROM_WIN32(ERROR_NOT_FOUND);
    if (SUCCEEDED(hr)) hr=db_endpoint_identity(device,&identity);
    if (SUCCEEDED(hr) && identity.flow!=eRender) hr=E_NOTIMPL;
    if (SUCCEEDED(hr) && identity.follows_default) hr=E_INVALIDARG;
    if (SUCCEEDED(hr)) hr=db_audio_call(&identity,4,(float)role,NULL,&reply);
    if (device) IMMDevice_Release(device);
    if (enumerator) IMMDeviceEnumerator_Release(enumerator);
    if (module) FreeLibrary(module);
    return hr;
}
static HRESULT WINAPI mix(DBPolicyVista *p,LPCWSTR id,WAVEFORMATEX **out)
{ (void)p;(void)id;if(out)*out=NULL;return E_NOTIMPL; }
static HRESULT WINAPI format(DBPolicyVista *p,LPCWSTR id,INT mode,WAVEFORMATEX **out)
{ (void)mode;return mix(p,id,out); }
static HRESULT WINAPI set_format(DBPolicyVista *p,LPCWSTR id,WAVEFORMATEX *a,WAVEFORMATEX *b)
{ (void)p;(void)id;(void)a;(void)b;return E_NOTIMPL; }
static HRESULT WINAPI period(DBPolicyVista *p,LPCWSTR id,INT mode,INT64 *a,INT64 *b)
{ (void)p;(void)id;(void)mode;(void)a;(void)b;return E_NOTIMPL; }
static HRESULT WINAPI set_period(DBPolicyVista *p,LPCWSTR id,INT64 *a)
{ (void)p;(void)id;(void)a;return E_NOTIMPL; }
static HRESULT WINAPI share(DBPolicyVista *p,LPCWSTR id,void *mode)
{ (void)p;(void)id;(void)mode;return E_NOTIMPL; }
static HRESULT WINAPI property(DBPolicyVista *p,LPCWSTR id,const PROPERTYKEY *key,PROPVARIANT *value)
{ (void)p;(void)id;(void)key;(void)value;return E_NOTIMPL; }
static HRESULT WINAPI visibility(DBPolicyVista *p,LPCWSTR id,INT visible)
{ (void)p;(void)id;(void)visible;return E_NOTIMPL; }
static const DBPolicyVistaVtbl vtable={query,addref,release,mix,format,set_format,period,set_period,
    share,share,property,property,set_default,visibility};

HRESULT db_policy_create(REFIID iid,void **out)
{
    Policy *p;
    HRESULT hr;
    if (!out) return E_POINTER;
    *out=NULL;
    p=CoTaskMemAlloc(sizeof(*p));
    if (!p) return E_OUTOFMEMORY;
    p->iface.lpVtbl=&vtable;p->refs=1;db_object_created();
    hr=query(&p->iface,iid,out);release(&p->iface);return hr;
}
