/* Read-only native friendly names; all other properties retain Wine behavior. */
#define COBJMACROS
#include "client.h"
#include <functiondiscoverykeys_devpkey.h>
#include <wchar.h>

typedef struct {
    IPropertyStore iface;
    LONG refs;
    IPropertyStore *real;
    HMODULE module;
    DBEndpointIdentity identity;
    BOOL mapped;
} Store;

static ULONG WINAPI addref(IPropertyStore *iface)
{ return InterlockedIncrement(&((Store *)iface)->refs); }
static ULONG WINAPI release(IPropertyStore *iface)
{
    Store *p=(Store *)iface;
    ULONG n=InterlockedDecrement(&p->refs);
    if (!n) {
        IPropertyStore_Release(p->real);FreeLibrary(p->module);
        CoTaskMemFree(p);db_object_destroyed();
    }
    return n;
}
static HRESULT WINAPI query(IPropertyStore *iface,REFIID iid,void **out)
{
    if (!out) return E_POINTER;
    *out=NULL;
    if (!IsEqualIID(iid,&IID_IUnknown) && !IsEqualIID(iid,&IID_IPropertyStore)) return E_NOINTERFACE;
    *out=iface;addref(iface);return S_OK;
}
static HRESULT WINAPI count(IPropertyStore *iface,DWORD *out)
{ return IPropertyStore_GetCount(((Store *)iface)->real,out); }
static HRESULT WINAPI at(IPropertyStore *iface,DWORD index,PROPERTYKEY *out)
{ return IPropertyStore_GetAt(((Store *)iface)->real,index,out); }

static void normalize_fallback(PROPVARIANT *value)
{
    static const WCHAR *prefixes[]={L"Speakers (",L"Microphone ("};
    if (value->vt!=VT_LPWSTR || !value->pwszVal) return;
    for (UINT i=0;i<2;++i) {
        WCHAR *text=value->pwszVal;
        SIZE_T prefix=wcslen(prefixes[i]),length=wcslen(text);
        /* Wine reloads a cached friendly name as a driver name and wraps it
         * again on each startup. Collapse repeated outer display wrappers. */
        while (length>2*prefix && !wcsncmp(text,prefixes[i],prefix)
                && !wcsncmp(text+prefix,prefixes[i],prefix) && text[length-1]==L')') {
            memmove(text,text+prefix,(length-prefix-1)*sizeof(WCHAR));
            length-=prefix+1;text[length]=0;
        }
    }
}
static HRESULT WINAPI get(IPropertyStore *iface,REFPROPERTYKEY key,PROPVARIANT *out)
{
    Store *p=(Store *)iface;
    LPWSTR description=NULL;
    if (!out || !key) return E_POINTER;
    if (p->mapped && IsEqualPropertyKey(*key,PKEY_Device_FriendlyName)
            && SUCCEEDED(db_audio_description(&p->identity,&description))) {
        ZeroMemory(out,sizeof(*out));out->vt=VT_LPWSTR;out->pwszVal=description;
        return S_OK;
    }
    HRESULT hr=IPropertyStore_GetValue(p->real,key,out);
    if (SUCCEEDED(hr) && IsEqualPropertyKey(*key,PKEY_Device_FriendlyName)) normalize_fallback(out);
    return hr;
}
static HRESULT WINAPI set(IPropertyStore *iface,REFPROPERTYKEY key,REFPROPVARIANT value)
{ return IPropertyStore_SetValue(((Store *)iface)->real,key,value); }
static HRESULT WINAPI commit(IPropertyStore *iface)
{ return IPropertyStore_Commit(((Store *)iface)->real); }
static IPropertyStoreVtbl vtable={query,addref,release,count,at,get,set,commit};

HRESULT db_store_create(IMMDevice *device,IPropertyStore *real,IPropertyStore **out)
{
    Store *p;
    if (!device || !real || !out) return E_POINTER;
    *out=NULL;
    p=CoTaskMemAlloc(sizeof(*p));
    if (!p) return E_OUTOFMEMORY;
    p->module=LoadLibraryExW(L"mmdevapi.dll",NULL,LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!p->module) { CoTaskMemFree(p);return E_FAIL; }
    p->iface.lpVtbl=&vtable;p->refs=1;p->real=real;IPropertyStore_AddRef(real);
    p->mapped=SUCCEEDED(db_endpoint_identity(device,&p->identity)) && !p->identity.follows_default;
    db_object_created();*out=&p->iface;return S_OK;
}
