/* Read-only by default. Exercise mode is for an explicitly memory-only server. */
#define COBJMACROS
#include <windows.h>
#include <initguid.h>
#include <stdio.h>
#include <wchar.h>
#include "policy.h"
const CLSID DB_CLSID_PolicyVista={0x294935ce,0xf637,0x4e7c,{0xa4,0x1b,0xab,0x25,0x54,0x60,0xb8,0x62}};
const IID DB_IID_PolicyVista={0x568b9108,0x44bf,0x40b4,{0x90,0x06,0x86,0xaf,0xe5,0xb5,0xa6,0x20}};
typedef struct { IMMNotificationClient iface; LONG refs, matched; HANDLE event; LPCWSTR expected; } Notify;
static ULONG WINAPI addref(IMMNotificationClient *p) { return InterlockedIncrement(&((Notify *)p)->refs); }
static ULONG WINAPI release(IMMNotificationClient *p) { return InterlockedDecrement(&((Notify *)p)->refs); }
static HRESULT WINAPI query(IMMNotificationClient *p,REFIID iid,void **out)
{
    if (!out) return E_POINTER;*out=NULL;
    if (!IsEqualIID(iid,&IID_IUnknown)&&!IsEqualIID(iid,&IID_IMMNotificationClient)) return E_NOINTERFACE;
    *out=p;addref(p);return S_OK;
}
static HRESULT WINAPI state(IMMNotificationClient *p,LPCWSTR id,DWORD value) { (void)p;(void)id;(void)value;return S_OK; }
static HRESULT WINAPI added(IMMNotificationClient *p,LPCWSTR id) { (void)p;(void)id;return S_OK; }
static HRESULT WINAPI changed(IMMNotificationClient *p,EDataFlow flow,ERole role,LPCWSTR id)
{
    Notify *n=(Notify *)p;
    if (flow==eRender && role==eConsole && id && n->expected && !wcscmp(id,n->expected)) {
        InterlockedExchange(&n->matched,1);SetEvent(n->event);
    }
    return S_OK;
}
static HRESULT WINAPI property(IMMNotificationClient *p,LPCWSTR id,const PROPERTYKEY key) { (void)p;(void)id;(void)key;return S_OK; }
static IMMNotificationClientVtbl notify_vtable={query,addref,release,state,added,added,changed,property};
static BOOL current_is(IMMDeviceEnumerator *e,LPCWSTR expected)
{
    IMMDevice *device=NULL;LPWSTR id=NULL;
    HRESULT hr=IMMDeviceEnumerator_GetDefaultAudioEndpoint(e,eRender,eConsole,&device);
    if (SUCCEEDED(hr)) hr=IMMDevice_GetId(device,&id);
    BOOL same=SUCCEEDED(hr)&&id&&!wcscmp(id,expected);
    CoTaskMemFree(id);if(device)IMMDevice_Release(device);return same;
}
int wmain(int argc,WCHAR **argv)
{
    HMODULE library=NULL;
    HRESULT (WINAPI *get_class)(REFCLSID,REFIID,void **)=NULL;
    HRESULT (WINAPI *can_unload)(void)=NULL;
    IMMDeviceEnumerator *enumerator=NULL;
    IMMDeviceCollection *devices=NULL;
    IMMDevice *initial=NULL;
    IClassFactory *factory=NULL;
    DBPolicyVista *policy=NULL;
    LPWSTR original=NULL,target=NULL,input=NULL;
    Notify notify={{&notify_vtable},1,0,NULL,NULL};
    BOOL exercise=argc==4 && !wcscmp(argv[3],L"--memory-exercise");
    BOOL registered=FALSE,physical=FALSE,identity_ok=FALSE,changed_ok=FALSE,restored=FALSE;
    BOOL notification_ok=FALSE,input_denied=FALSE,role_denied=FALSE,lifetime=FALSE;
    UINT setters=0,count=0;
    HRESULT hr=E_FAIL;
    FILE *report;
    if (argc<3 || argc>4 || (argc==4&&!exercise)) return 2;
    if (exercise) {
        WCHAR guard[4];
        if (GetEnvironmentVariableW(L"DECKBRIDGE_POLICY_MEMORY_TEST",guard,4)!=1 || guard[0]!=L'1') return 3;
    }
    if (FAILED(CoInitializeEx(NULL,COINIT_MULTITHREADED))) return 4;
    library=LoadLibraryW(argv[2]);
    if (!library) goto done;
    get_class=(HRESULT(WINAPI *)(REFCLSID,REFIID,void **))(void *)GetProcAddress(library,"DllGetClassObject");
    can_unload=(HRESULT(WINAPI *)(void))(void *)GetProcAddress(library,"DllCanUnloadNow");
    if (!get_class||!can_unload) goto done;
    hr=get_class(&CLSID_MMDeviceEnumerator,&IID_IClassFactory,(void **)&factory);
    if (SUCCEEDED(hr)) hr=IClassFactory_CreateInstance(factory,NULL,&IID_IMMDeviceEnumerator,(void **)&enumerator);
    if (factory) { IClassFactory_Release(factory);factory=NULL; }
    if (FAILED(hr)) goto done;
    hr=get_class(&DB_CLSID_PolicyVista,&IID_IClassFactory,(void **)&factory);
    if (SUCCEEDED(hr)) hr=IClassFactory_CreateInstance(factory,NULL,&DB_IID_PolicyVista,(void **)&policy);
    if (factory) { IClassFactory_Release(factory);factory=NULL; }
    if (FAILED(hr)) goto done;
    IUnknown *identity=NULL;
    hr=policy->lpVtbl->QueryInterface(policy,&IID_IUnknown,(void **)&identity);
    identity_ok=SUCCEEDED(hr)&&identity==(IUnknown *)policy;
    if(identity)IUnknown_Release(identity);
    hr=IMMDeviceEnumerator_GetDefaultAudioEndpoint(enumerator,eRender,eConsole,&initial);
    if (SUCCEEDED(hr)) hr=IMMDevice_GetId(initial,&original);
    if (SUCCEEDED(hr)) {
        DBEndpointIdentity mapped;
        physical=SUCCEEDED(db_endpoint_identity(initial,&mapped))&&!mapped.follows_default;
    }
    if (!exercise || FAILED(hr)) goto done;
    hr=IMMDeviceEnumerator_EnumAudioEndpoints(enumerator,eAll,DEVICE_STATE_ACTIVE,&devices);
    if(SUCCEEDED(hr))hr=IMMDeviceCollection_GetCount(devices,&count);
    for(UINT i=0;SUCCEEDED(hr)&&i<count;++i) {
        IMMDevice *d=NULL;DBEndpointIdentity mapped;
        HRESULT item=IMMDeviceCollection_Item(devices,i,&d);
        if(SUCCEEDED(item))item=db_endpoint_identity(d,&mapped);
        if(SUCCEEDED(item)&&!mapped.follows_default) {
            LPWSTR id=NULL;IMMDevice_GetId(d,&id);
            if(id&&mapped.flow==eRender&&!target&&wcscmp(id,original)) { target=id;id=NULL; }
            else if(id&&mapped.flow==eCapture&&!input) { input=id;id=NULL; }
            CoTaskMemFree(id);
        }
        if(d)IMMDevice_Release(d);
    }
    if(!target) { hr=HRESULT_FROM_WIN32(ERROR_NOT_FOUND);goto done; }
    notify.event=CreateEventW(NULL,TRUE,FALSE,NULL);notify.expected=target;
    if(!notify.event) { hr=E_OUTOFMEMORY;goto done; }
    hr=IMMDeviceEnumerator_RegisterEndpointNotificationCallback(enumerator,&notify.iface);
    if(FAILED(hr))goto done;
    registered=TRUE;
    role_denied=policy->lpVtbl->SetDefaultEndpoint(policy,target,eCommunications)==E_NOTIMPL;
    input_denied=input&&policy->lpVtbl->SetDefaultEndpoint(policy,input,eConsole)==E_NOTIMPL;
    ++setters;hr=policy->lpVtbl->SetDefaultEndpoint(policy,target,eConsole);
    if(SUCCEEDED(hr)) {
        changed_ok=current_is(enumerator,target);
        notification_ok=WaitForSingleObject(notify.event,3000)==WAIT_OBJECT_0&&notify.matched;
    }
    notify.expected=original;InterlockedExchange(&notify.matched,0);ResetEvent(notify.event);
    ++setters;
    if(SUCCEEDED(policy->lpVtbl->SetDefaultEndpoint(policy,original,eConsole)))
        restored=current_is(enumerator,original)&&WaitForSingleObject(notify.event,3000)==WAIT_OBJECT_0&&notify.matched;
done:
    if(registered)IMMDeviceEnumerator_UnregisterEndpointNotificationCallback(enumerator,&notify.iface);
    if(devices)IMMDeviceCollection_Release(devices);
    if(initial)IMMDevice_Release(initial);
    if(enumerator)IMMDeviceEnumerator_Release(enumerator);
    if(policy)policy->lpVtbl->Release(policy);
    if(can_unload) {
        ULONGLONG deadline=GetTickCount64()+5000;
        while(can_unload()!=S_OK&&GetTickCount64()<deadline)Sleep(20);
        lifetime=can_unload()==S_OK&&notify.refs==1;
    }
    report=_wfopen(argv[1],L"wb");
    if(report) {
        fprintf(report,"{\"version\":1,\"hresult\":%lu,\"physical_default\":%s,\"identity_ok\":%s,\"changed\":%s,\"notification\":%s,\"restored\":%s,\"communications_denied\":%s,\"input_denied\":%s,\"lifetime_ok\":%s,\"setters_called\":%u}\n",
            (unsigned long)hr,physical?"true":"false",identity_ok?"true":"false",changed_ok?"true":"false",notification_ok?"true":"false",restored?"true":"false",role_denied?"true":"false",input_denied?"true":"false",lifetime?"true":"false",setters);
        fclose(report);
    }
    if(lifetime) { CoTaskMemFree(original);CoTaskMemFree(target);CoTaskMemFree(input);if(notify.event)CloseHandle(notify.event); }
    CoUninitialize();if(library)FreeLibrary(library);
    return !report||FAILED(hr)||!physical||!identity_ok||!lifetime||(exercise&&(!changed_ok||!notification_ok||!restored||!role_denied||!input_denied));
}
