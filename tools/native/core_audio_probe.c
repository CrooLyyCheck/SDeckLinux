/* Read-only x64 Core Audio ABI probe. No setters or input events. */
#define COBJMACROS
#include <windows.h>
#include <initguid.h>
#include <mmdeviceapi.h>
#include <endpointvolume.h>
#include <stdio.h>

int wmain(int argc, wchar_t **argv)
{
    IMMDeviceEnumerator *enumerator = NULL;
    IMMDeviceCollection *devices = NULL;
    HRESULT init, hr;
    UINT count = 0, readable = 0, muted = 0;
    float minimum = 2.0f, maximum = -1.0f;
    FILE *output;
    if (argc != 2) return 2;
    init = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    if (FAILED(init)) return 3;
    hr = CoCreateInstance(&CLSID_MMDeviceEnumerator, NULL, CLSCTX_INPROC_SERVER,
            &IID_IMMDeviceEnumerator, (void **)&enumerator);
    if (SUCCEEDED(hr))
        hr = IMMDeviceEnumerator_EnumAudioEndpoints(enumerator, eAll, DEVICE_STATE_ACTIVE, &devices);
    if (SUCCEEDED(hr)) hr = IMMDeviceCollection_GetCount(devices, &count);
    for (UINT i = 0; SUCCEEDED(hr) && i < count; ++i) {
        IMMDevice *device = NULL;
        IAudioEndpointVolume *volume = NULL;
        HRESULT item_hr = IMMDeviceCollection_Item(devices, i, &device);
        if (SUCCEEDED(item_hr))
            item_hr = IMMDevice_Activate(device, &IID_IAudioEndpointVolume,
                    CLSCTX_INPROC_SERVER, NULL, (void **)&volume);
        if (SUCCEEDED(item_hr)) {
            float scalar = 0;
            BOOL mute = FALSE;
            item_hr = IAudioEndpointVolume_GetMasterVolumeLevelScalar(volume, &scalar);
            if (SUCCEEDED(item_hr)) item_hr = IAudioEndpointVolume_GetMute(volume, &mute);
            if (SUCCEEDED(item_hr)) {
                ++readable;
                if (mute) ++muted;
                if (scalar < minimum) minimum = scalar;
                if (scalar > maximum) maximum = scalar;
            }
        }
        if (volume) IAudioEndpointVolume_Release(volume);
        if (device) IMMDevice_Release(device);
    }
    output = _wfopen(argv[1], L"wb");
    if (output) {
        fprintf(output, "{\"version\":1,\"hresult\":%lu,\"devices\":%u,"
                "\"readable\":%u,\"muted\":%u,\"minimum\":%.8f,\"maximum\":%.8f,"
                "\"setters_called\":0}\n", (unsigned long)hr, count, readable, muted,
                readable ? minimum : 0.0f, readable ? maximum : 0.0f);
        fclose(output);
    }
    if (devices) IMMDeviceCollection_Release(devices);
    if (enumerator) IMMDeviceEnumerator_Release(enumerator);
    CoUninitialize();
    return !output || FAILED(hr) || readable != count;
}
