#ifndef DECKBRIDGE_POLICY_H
#define DECKBRIDGE_POLICY_H
#include "client.h"
#include <mmreg.h>
/* Observed IPolicyConfigVista x64 ABI, AudioDeviceLib fb7b31b. */
typedef struct DBPolicyVista DBPolicyVista;
typedef struct {
    HRESULT (WINAPI *QueryInterface)(DBPolicyVista *,REFIID,void **);
    ULONG (WINAPI *AddRef)(DBPolicyVista *);
    ULONG (WINAPI *Release)(DBPolicyVista *);
    HRESULT (WINAPI *GetMixFormat)(DBPolicyVista *,LPCWSTR,WAVEFORMATEX **);
    HRESULT (WINAPI *GetDeviceFormat)(DBPolicyVista *,LPCWSTR,INT,WAVEFORMATEX **);
    HRESULT (WINAPI *SetDeviceFormat)(DBPolicyVista *,LPCWSTR,WAVEFORMATEX *,WAVEFORMATEX *);
    HRESULT (WINAPI *GetProcessingPeriod)(DBPolicyVista *,LPCWSTR,INT,INT64 *,INT64 *);
    HRESULT (WINAPI *SetProcessingPeriod)(DBPolicyVista *,LPCWSTR,INT64 *);
    HRESULT (WINAPI *GetShareMode)(DBPolicyVista *,LPCWSTR,void *);
    HRESULT (WINAPI *SetShareMode)(DBPolicyVista *,LPCWSTR,void *);
    HRESULT (WINAPI *GetPropertyValue)(DBPolicyVista *,LPCWSTR,const PROPERTYKEY *,PROPVARIANT *);
    HRESULT (WINAPI *SetPropertyValue)(DBPolicyVista *,LPCWSTR,const PROPERTYKEY *,PROPVARIANT *);
    HRESULT (WINAPI *SetDefaultEndpoint)(DBPolicyVista *,LPCWSTR,ERole);
    HRESULT (WINAPI *SetEndpointVisibility)(DBPolicyVista *,LPCWSTR,INT);
} DBPolicyVistaVtbl;
struct DBPolicyVista { const DBPolicyVistaVtbl *lpVtbl; };
#endif
