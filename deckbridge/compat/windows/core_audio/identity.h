#ifndef DECKBRIDGE_ENDPOINT_IDENTITY_H
#define DECKBRIDGE_ENDPOINT_IDENTITY_H
#include <windows.h>
#include <mmdeviceapi.h>

/* Wine 11.20 winepulse endpoint identity, not a friendly-name heuristic. */
typedef struct {
    EDataFlow flow;
    WCHAR name[4096];
    BOOL follows_default;
} DBEndpointIdentity;

HRESULT db_endpoint_identity(IMMDevice *device, DBEndpointIdentity *identity);
#endif
