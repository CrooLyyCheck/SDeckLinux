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
__declspec(dllexport) HRESULT db_volume_create(IMMDevice *device, REFIID iid, void **result);
void db_object_created(void);
void db_object_destroyed(void);
#endif
