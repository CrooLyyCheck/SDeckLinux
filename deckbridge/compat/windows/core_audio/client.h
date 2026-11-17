#ifndef DECKBRIDGE_AUDIO_CLIENT_H
#define DECKBRIDGE_AUDIO_CLIENT_H
#include "identity.h"
typedef struct {
    char magic[4];
    DWORD status;
    float volume;
    DWORD mute;
    DWORD count;
    float channels[64];
    GUID context;
} DBReply;
typedef struct DBSubscription DBSubscription;
HRESULT db_audio_call(const DBEndpointIdentity *identity, WORD operation, float value, LPCGUID context, DBReply *reply);
HRESULT db_audio_subscribe(const DBEndpointIdentity *identity, DBReply *reply, DBSubscription **result);
HRESULT db_audio_next(DBSubscription *subscription, HANDLE stop, DBReply *reply);
void db_audio_close(DBSubscription *subscription);
HRESULT db_audio_default(DBEndpointIdentity *identity);
HRESULT db_audio_subscribe_default(DBEndpointIdentity *identity, DBSubscription **result);
HRESULT db_audio_next_default(DBSubscription *subscription, HANDLE stop, DBEndpointIdentity *identity);
HRESULT db_wine_enumerator(IMMDeviceEnumerator **result, HMODULE *module);
HRESULT db_find_native_device(IMMDeviceEnumerator *real, const DBEndpointIdentity *identity, IMMDevice **result);
HRESULT db_policy_create(REFIID iid, void **result);
extern const CLSID DB_CLSID_PolicyVista;
extern const IID DB_IID_PolicyVista;
typedef struct DBEnumEvents DBEnumEvents;
DBEnumEvents *db_enum_events_create(IMMDeviceEnumerator *real);
void db_enum_events_close(DBEnumEvents *events);
HRESULT db_enum_register(DBEnumEvents *events, IMMNotificationClient *client);
HRESULT db_enum_unregister(DBEnumEvents *events, IMMNotificationClient *client);
__declspec(dllexport) HRESULT db_volume_create(IMMDevice *device, REFIID iid, void **result);
void db_object_created(void);
void db_object_destroyed(void);
#endif
