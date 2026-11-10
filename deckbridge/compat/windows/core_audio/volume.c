/* Experimental endpoint-volume implementation. No COM registration on install.
 * Scalar/mute operations are real native RPC. Unsupported interfaces fail.
 */
#define COBJMACROS
#include "client.h"
#include <initguid.h>
#include <endpointvolume.h>
#include <math.h>
#define RECONNECT_ATTEMPTS 6

typedef struct DBWorker DBWorker;
typedef struct {
    IAudioEndpointVolumeEx iface;
    LONG references;
    DBEndpointIdentity identity;
    CRITICAL_SECTION lock;
    IAudioEndpointVolumeCallback *callbacks[16];
    UINT callback_count;
    DBWorker *worker;
} DBVolume;
struct DBWorker { DBVolume *object; DBSubscription *subscription; HANDLE stop; HMODULE module; };

static ULONG WINAPI volume_addref(IAudioEndpointVolumeEx *iface)
{
    return InterlockedIncrement(&((DBVolume *)iface)->references);
}

static ULONG WINAPI volume_release(IAudioEndpointVolumeEx *iface)
{
    DBVolume *object = (DBVolume *)iface;
    ULONG count = InterlockedDecrement(&object->references);
    if (!count) {
        for (UINT i = 0; i < object->callback_count; ++i)
            IAudioEndpointVolumeCallback_Release(object->callbacks[i]);
        DeleteCriticalSection(&object->lock);
        CoTaskMemFree(object);
        db_object_destroyed();
    }
    return count;
}

static HRESULT WINAPI volume_query(IAudioEndpointVolumeEx *iface, REFIID iid, void **result)
{
    if (!result) return E_POINTER;
    *result = NULL;
    if (!IsEqualIID(iid, &IID_IUnknown) && !IsEqualIID(iid, &IID_IAudioEndpointVolume)
            && !IsEqualIID(iid, &IID_IAudioEndpointVolumeEx)) return E_NOINTERFACE;
    *result = iface;
    volume_addref(iface);
    return S_OK;
}

static HRESULT read_volume(IAudioEndpointVolumeEx *iface, DBReply *reply)
{
    return db_audio_call(&((DBVolume *)iface)->identity, 0, 0, NULL, reply);
}

static void notify_callbacks(DBWorker *worker, const DBReply *reply)
{
    DBVolume *object = worker->object;
    IAudioEndpointVolumeCallback *callbacks[16];
    UINT count = 0;
    struct {
        AUDIO_VOLUME_NOTIFICATION_DATA data;
        float remaining_channels[63];
    } notification;
    ZeroMemory(&notification, sizeof(notification));
    notification.data.guidEventContext = reply->context;
    notification.data.bMuted = reply->mute;
    notification.data.fMasterVolume = reply->volume;
    notification.data.nChannels = reply->count;
    for (DWORD i = 0; i < reply->count; ++i) notification.data.afChannelVolumes[i] = reply->channels[i];
    EnterCriticalSection(&object->lock);
    if (object->worker == worker && WaitForSingleObject(worker->stop, 0) == WAIT_TIMEOUT) {
        count = object->callback_count;
        for (UINT i = 0; i < count; ++i) {
            callbacks[i] = object->callbacks[i];
            IAudioEndpointVolumeCallback_AddRef(callbacks[i]);
        }
    }
    LeaveCriticalSection(&object->lock);
    /* Never hold the registration lock while calling client code. */
    for (UINT i = 0; i < count; ++i) {
        IAudioEndpointVolumeCallback_OnNotify(callbacks[i], &notification.data);
        IAudioEndpointVolumeCallback_Release(callbacks[i]);
    }
}

static DWORD WINAPI notification_worker(void *parameter)
{
    DBWorker *worker = parameter;
    DBVolume *object = worker->object;
    HMODULE module = worker->module;
    DBReply reply;
    DWORD delay = 250;
    while (WaitForSingleObject(worker->stop, 0) == WAIT_TIMEOUT) {
        HRESULT hr = db_audio_next(worker->subscription, worker->stop, &reply);
        if (hr == S_FALSE) break;
        if (SUCCEEDED(hr)) { notify_callbacks(worker, &reply); continue; }
        db_audio_close(worker->subscription);
        worker->subscription = NULL;
        /* Read-only recovery. A lost connection never replays a setter. */
        for (UINT attempt = 0; attempt < RECONNECT_ATTEMPTS; ++attempt) {
            if (WaitForSingleObject(worker->stop, delay) != WAIT_TIMEOUT) break;
            hr = db_audio_subscribe(&object->identity, &reply, &worker->subscription);
            if (SUCCEEDED(hr)) {
                delay = 250;
                notify_callbacks(worker, &reply); /* Resynchronize after outage. */
                break;
            }
            delay = delay < 2500 ? delay * 2 : 5000;
        }
        if (!worker->subscription) break;
    }
    EnterCriticalSection(&object->lock);
    if (object->worker == worker) object->worker = NULL;
    LeaveCriticalSection(&object->lock);
    db_audio_close(worker->subscription);
    CloseHandle(worker->stop);
    CoTaskMemFree(worker);
    volume_release(&object->iface); /* Keeps DLL/object alive until this thread exits. */
    FreeLibraryAndExitThread(module, 0);
}

static HRESULT WINAPI volume_register(IAudioEndpointVolumeEx *iface, IAudioEndpointVolumeCallback *notify)
{
    DBVolume *object = (DBVolume *)iface;
    DBWorker *worker = NULL;
    DBReply initial;
    HANDLE thread;
    HRESULT hr = S_OK;
    if (!notify) return E_POINTER;
    EnterCriticalSection(&object->lock);
    for (UINT i = 0; i < object->callback_count; ++i)
        if (object->callbacks[i] == notify) { hr = E_INVALIDARG; goto done; }
    if (object->callback_count == 16) { hr = E_OUTOFMEMORY; goto done; }
    if (!object->worker) {
        worker = CoTaskMemAlloc(sizeof(*worker));
        if (!worker) { hr = E_OUTOFMEMORY; goto done; }
        ZeroMemory(worker, sizeof(*worker));
        worker->object = object;
        worker->stop = CreateEventW(NULL, TRUE, FALSE, NULL);
        if (!worker->stop) { hr = E_OUTOFMEMORY; goto failed; }
        if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
                (LPCWSTR)(void *)&notification_worker, &worker->module)) {
            hr = E_FAIL;
            goto failed;
        }
        hr = db_audio_subscribe(&object->identity, &initial, &worker->subscription);
        if (FAILED(hr)) goto failed;
        volume_addref(iface);
        object->worker = worker;
        thread = CreateThread(NULL, 0, notification_worker, worker, 0, NULL);
        if (!thread) {
            object->worker = NULL;
            volume_release(iface);
            hr = E_OUTOFMEMORY;
            goto failed;
        }
        CloseHandle(thread); /* Worker owns its stop event and subscription. */
    }
    IAudioEndpointVolumeCallback_AddRef(notify);
    object->callbacks[object->callback_count++] = notify;
    goto done;
failed:
    db_audio_close(worker->subscription);
    if (worker->stop) CloseHandle(worker->stop);
    if (worker->module) FreeLibrary(worker->module);
    CoTaskMemFree(worker);
done:
    LeaveCriticalSection(&object->lock);
    return hr;
}

static HRESULT WINAPI volume_unregister(IAudioEndpointVolumeEx *iface, IAudioEndpointVolumeCallback *notify)
{
    DBVolume *object = (DBVolume *)iface;
    UINT index;
    if (!notify) return E_POINTER;
    EnterCriticalSection(&object->lock);
    for (index = 0; index < object->callback_count; ++index)
        if (object->callbacks[index] == notify) break;
    if (index == object->callback_count) {
        LeaveCriticalSection(&object->lock);
        return E_INVALIDARG;
    }
    object->callbacks[index] = object->callbacks[--object->callback_count];
    if (!object->callback_count && object->worker) {
        SetEvent(object->worker->stop);
        object->worker = NULL;
    }
    LeaveCriticalSection(&object->lock);
    IAudioEndpointVolumeCallback_Release(notify);
    return S_OK;
}

static HRESULT WINAPI volume_channels(IAudioEndpointVolumeEx *iface, UINT *count)
{
    DBReply reply;
    HRESULT hr;
    if (!count) return E_POINTER;
    *count = 0;
    hr = read_volume(iface, &reply);
    if (SUCCEEDED(hr)) *count = reply.count;
    return hr;
}

static HRESULT WINAPI volume_set_scalar(IAudioEndpointVolumeEx *iface, float value, LPCGUID context)
{
    DBReply reply;
    if (!isfinite(value) || value < 0 || value > 1) return E_INVALIDARG;
    return db_audio_call(&((DBVolume *)iface)->identity, 1, value, context, &reply);
}

static HRESULT WINAPI volume_get_scalar(IAudioEndpointVolumeEx *iface, float *value)
{
    DBReply reply;
    HRESULT hr;
    if (!value) return E_POINTER;
    *value = 0;
    hr = read_volume(iface, &reply);
    if (SUCCEEDED(hr)) *value = reply.volume;
    return hr;
}

static HRESULT WINAPI volume_get_channel(IAudioEndpointVolumeEx *iface, UINT channel, float *value)
{
    DBReply reply;
    HRESULT hr;
    if (!value) return E_POINTER;
    *value = 0;
    hr = read_volume(iface, &reply);
    if (FAILED(hr)) return hr;
    if (channel >= reply.count) return E_INVALIDARG;
    *value = reply.channels[channel];
    return S_OK;
}

static HRESULT WINAPI volume_set_mute(IAudioEndpointVolumeEx *iface, BOOL mute, LPCGUID context)
{
    DBReply reply;
    return db_audio_call(&((DBVolume *)iface)->identity, 2, !!mute, context, &reply);
}

static HRESULT WINAPI volume_get_mute(IAudioEndpointVolumeEx *iface, BOOL *mute)
{
    DBReply reply;
    HRESULT hr;
    if (!mute) return E_POINTER;
    *mute = FALSE;
    hr = read_volume(iface, &reply);
    if (SUCCEEDED(hr)) *mute = !!reply.mute;
    return hr;
}

static HRESULT WINAPI volume_hardware(IAudioEndpointVolumeEx *iface, DWORD *mask)
{
    (void)iface;
    if (!mask) return E_POINTER;
    *mask = 0; /* Native control is software; no hardware acceleration claimed. */
    return S_OK;
}

static HRESULT WINAPI volume_set_db(IAudioEndpointVolumeEx *iface, float value, LPCGUID context)
{
    (void)iface; (void)value; (void)context;
    return E_NOTIMPL;
}
static HRESULT WINAPI volume_get_db(IAudioEndpointVolumeEx *iface, float *value)
{
    (void)iface;
    return value ? E_NOTIMPL : E_POINTER;
}
static HRESULT WINAPI volume_set_channel(IAudioEndpointVolumeEx *iface, UINT channel, float value, LPCGUID context)
{
    (void)iface; (void)channel; (void)value; (void)context;
    return E_NOTIMPL;
}
static HRESULT WINAPI volume_get_channel_db(IAudioEndpointVolumeEx *iface, UINT channel, float *value)
{
    (void)iface; (void)channel;
    return value ? E_NOTIMPL : E_POINTER;
}
static HRESULT WINAPI volume_steps(IAudioEndpointVolumeEx *iface, UINT *step, UINT *count)
{
    (void)iface;
    return step && count ? E_NOTIMPL : E_POINTER;
}
static HRESULT WINAPI volume_step(IAudioEndpointVolumeEx *iface, LPCGUID context)
{
    (void)iface; (void)context;
    return E_NOTIMPL;
}
static HRESULT WINAPI volume_range(IAudioEndpointVolumeEx *iface, float *min, float *max, float *step)
{
    (void)iface;
    return min && max && step ? E_NOTIMPL : E_POINTER;
}
static HRESULT WINAPI volume_channel_range(IAudioEndpointVolumeEx *iface, UINT channel, float *min, float *max, float *step)
{
    (void)channel;
    return volume_range(iface, min, max, step);
}

static IAudioEndpointVolumeExVtbl vtable = {
    volume_query, volume_addref, volume_release, volume_register, volume_unregister,
    volume_channels, volume_set_db, volume_set_scalar, volume_get_db, volume_get_scalar,
    volume_set_channel, volume_set_channel, volume_get_channel_db, volume_get_channel,
    volume_set_mute, volume_get_mute, volume_steps, volume_step, volume_step,
    volume_hardware, volume_range, volume_channel_range
};

HRESULT db_volume_create(IMMDevice *device, REFIID iid, void **result)
{
    DBVolume *object;
    HRESULT hr;
    if (!result) return E_POINTER;
    *result = NULL;
    object = CoTaskMemAlloc(sizeof(*object));
    if (!object) return E_OUTOFMEMORY;
    object->iface.lpVtbl = &vtable;
    object->references = 1;
    object->callback_count = 0;
    object->worker = NULL;
    InitializeCriticalSection(&object->lock);
    db_object_created();
    hr = db_endpoint_identity(device, &object->identity);
    if (SUCCEEDED(hr)) hr = volume_query(&object->iface, iid, result);
    volume_release(&object->iface);
    return hr;
}
