/* Native output-default notifications, preserving Wine's other device events. */
#define COBJMACROS
#include "client.h"
#include <wchar.h>

typedef struct Registration Registration;
struct DBEnumEvents { CRITICAL_SECTION lock; IMMDeviceEnumerator *real; Registration *items[16]; UINT count; };
struct Registration {
    IMMNotificationClient iface;
    LONG refs, active;
    IMMNotificationClient *client;
    IMMDeviceEnumerator *real;
    HMODULE wine;
    HANDLE stop;
    DBSubscription *subscription;
    DBEndpointIdentity previous;
};
static ULONG WINAPI addref(IMMNotificationClient *iface)
{ return InterlockedIncrement(&((Registration *)iface)->refs); }
static ULONG WINAPI release(IMMNotificationClient *iface)
{
    Registration *r=(Registration *)iface;
    ULONG n=InterlockedDecrement(&r->refs);
    if (!n) {
        if (r->subscription) db_audio_close(r->subscription);
        if (r->stop) CloseHandle(r->stop);
        IMMNotificationClient_Release(r->client);
        IMMDeviceEnumerator_Release(r->real);
        if (r->wine) FreeLibrary(r->wine);
        CoTaskMemFree(r);db_object_destroyed();
    }
    return n;
}
static HRESULT WINAPI query(IMMNotificationClient *iface,REFIID iid,void **out)
{
    if (!out) return E_POINTER;
    *out=NULL;
    if (!IsEqualIID(iid,&IID_IUnknown) && !IsEqualIID(iid,&IID_IMMNotificationClient)) return E_NOINTERFACE;
    *out=iface;addref(iface);return S_OK;
}
static BOOL active(Registration *r) { return InterlockedCompareExchange(&r->active,0,0)!=0; }
static HRESULT WINAPI state(IMMNotificationClient *iface,LPCWSTR id,DWORD value)
{ Registration *r=(Registration *)iface;return active(r)?IMMNotificationClient_OnDeviceStateChanged(r->client,id,value):S_OK; }
static HRESULT WINAPI added(IMMNotificationClient *iface,LPCWSTR id)
{ Registration *r=(Registration *)iface;return active(r)?IMMNotificationClient_OnDeviceAdded(r->client,id):S_OK; }
static HRESULT WINAPI removed(IMMNotificationClient *iface,LPCWSTR id)
{ Registration *r=(Registration *)iface;return active(r)?IMMNotificationClient_OnDeviceRemoved(r->client,id):S_OK; }
static HRESULT WINAPI changed(IMMNotificationClient *iface,EDataFlow flow,ERole role,LPCWSTR id)
{
    Registration *r=(Registration *)iface;
    if (flow==eRender && (role==eConsole || role==eMultimedia)) return S_OK;
    return active(r)?IMMNotificationClient_OnDefaultDeviceChanged(r->client,flow,role,id):S_OK;
}
static HRESULT WINAPI property(IMMNotificationClient *iface,LPCWSTR id,const PROPERTYKEY key)
{ Registration *r=(Registration *)iface;return active(r)?IMMNotificationClient_OnPropertyValueChanged(r->client,id,key):S_OK; }
static IMMNotificationClientVtbl vtable={query,addref,release,state,added,removed,changed,property};

static BOOL deliver(Registration *r,const DBEndpointIdentity *identity)
{
    IMMDevice *device=NULL;
    LPWSTR id=NULL;
    HRESULT hr=S_OK;
    if (!wcscmp(r->previous.name,identity->name)) return TRUE;
    if (identity->name[0]) {
        hr=db_find_native_device(r->real,identity,&device);
        if (SUCCEEDED(hr)) hr=IMMDevice_GetId(device,&id);
    }
    if (device) IMMDevice_Release(device);
    if (FAILED(hr)) return FALSE;
    if (active(r)) {
        IMMNotificationClient_OnDefaultDeviceChanged(r->client,eRender,eConsole,id);
        IMMNotificationClient_OnDefaultDeviceChanged(r->client,eRender,eMultimedia,id);
    }
    r->previous=*identity;
    CoTaskMemFree(id);
    return TRUE;
}
typedef struct { Registration *registration; HMODULE self; } Worker;
static DWORD WINAPI worker(void *parameter)
{
    Worker *w=parameter;
    Registration *r=w->registration;
    HMODULE self=w->self;
    DBEndpointIdentity identity;
    CoTaskMemFree(w);
    while (WaitForSingleObject(r->stop,0)==WAIT_TIMEOUT) {
        HRESULT hr=db_audio_next_default(r->subscription,r->stop,&identity);
        if (hr==S_FALSE) break;
        if ((SUCCEEDED(hr) || hr==HRESULT_FROM_WIN32(ERROR_NOT_FOUND)) && deliver(r,&identity)) continue;
        db_audio_close(r->subscription);r->subscription=NULL;
        DWORD delay=250;
        for (UINT attempt=0;attempt<6;++attempt) {
            if (WaitForSingleObject(r->stop,delay)!=WAIT_TIMEOUT) break;
            hr=db_audio_subscribe_default(&identity,&r->subscription);
            if (SUCCEEDED(hr) && deliver(r,&identity)) break;
            db_audio_close(r->subscription);r->subscription=NULL;
            delay=delay<2500?delay*2:5000;
        }
        if (!r->subscription) break;
    }
    db_audio_close(r->subscription);r->subscription=NULL;
    release(&r->iface);
    FreeLibraryAndExitThread(self,0);
}

DBEnumEvents *db_enum_events_create(IMMDeviceEnumerator *real)
{
    DBEnumEvents *events=CoTaskMemAlloc(sizeof(*events));
    if (!events) return NULL;
    InitializeCriticalSection(&events->lock);events->real=real;events->count=0;
    return events;
}
HRESULT db_enum_register(DBEnumEvents *events,IMMNotificationClient *client)
{
    Registration *r=NULL;
    Worker *w=NULL;
    HANDLE thread;
    HRESULT hr=S_OK;
    BOOL registered=FALSE;
    if (!client) return E_POINTER;
    EnterCriticalSection(&events->lock);
    for (UINT i=0;i<events->count;++i)
        if (events->items[i]->client==client) { hr=E_INVALIDARG;goto done; }
    if (events->count==16) { hr=E_OUTOFMEMORY;goto done; }
    r=CoTaskMemAlloc(sizeof(*r));w=CoTaskMemAlloc(sizeof(*w));
    if (!r || !w) { CoTaskMemFree(r);CoTaskMemFree(w);r=NULL;w=NULL;hr=E_OUTOFMEMORY;goto done; }
    ZeroMemory(r,sizeof(*r));ZeroMemory(w,sizeof(*w));
    r->iface.lpVtbl=&vtable;r->refs=1;r->active=1;r->client=client;r->real=events->real;
    IMMNotificationClient_AddRef(client);IMMDeviceEnumerator_AddRef(r->real);db_object_created();
    r->wine=LoadLibraryExW(L"mmdevapi.dll",NULL,LOAD_LIBRARY_SEARCH_SYSTEM32);
    r->stop=CreateEventW(NULL,TRUE,FALSE,NULL);
    if (!r->wine || !r->stop) { hr=E_OUTOFMEMORY;goto failed; }
    hr=db_audio_subscribe_default(&r->previous,&r->subscription);
    if (FAILED(hr)) goto failed;
    hr=IMMDeviceEnumerator_RegisterEndpointNotificationCallback(r->real,&r->iface);
    if (FAILED(hr)) goto failed;
    registered=TRUE;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,(LPCWSTR)(void *)&worker,&w->self)) { hr=E_FAIL;goto failed; }
    w->registration=r;addref(&r->iface);
    thread=CreateThread(NULL,0,worker,w,0,NULL);
    if (!thread) { release(&r->iface);hr=E_OUTOFMEMORY;goto failed; }
    CloseHandle(thread);w=NULL;events->items[events->count++]=r;goto done;
failed:
    if (registered) IMMDeviceEnumerator_UnregisterEndpointNotificationCallback(r->real,&r->iface);
    if (w && w->self) FreeLibrary(w->self);
    if (r) release(&r->iface);
    CoTaskMemFree(w);
done:
    LeaveCriticalSection(&events->lock);return hr;
}
HRESULT db_enum_unregister(DBEnumEvents *events,IMMNotificationClient *client)
{
    Registration *r=NULL;
    HRESULT hr;
    if (!client) return E_POINTER;
    EnterCriticalSection(&events->lock);
    for (UINT i=0;i<events->count;++i) if (events->items[i]->client==client) {
        r=events->items[i];events->items[i]=events->items[--events->count];break;
    }
    LeaveCriticalSection(&events->lock);
    if (!r) return HRESULT_FROM_WIN32(ERROR_NOT_FOUND);
    InterlockedExchange(&r->active,0);SetEvent(r->stop);
    hr=IMMDeviceEnumerator_UnregisterEndpointNotificationCallback(r->real,&r->iface);
    release(&r->iface);return hr;
}
void db_enum_events_close(DBEnumEvents *events)
{
    if (!events) return;
    while (events->count) db_enum_unregister(events,events->items[0]->client);
    DeleteCriticalSection(&events->lock);CoTaskMemFree(events);
}
