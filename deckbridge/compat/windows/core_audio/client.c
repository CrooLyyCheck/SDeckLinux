#include <winsock2.h>
#include <ws2tcpip.h>
#include "client.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#define RPC_DEADLINE_MS 3000

typedef struct {
    char magic[4];
    WORD operation, flow;
    DWORD length;
    float value;
    GUID context;
} DBRequest;
_Static_assert(sizeof(DBRequest) == 32, "request ABI");
_Static_assert(sizeof(DBReply) == 292, "reply ABI");
struct DBSubscription { SOCKET socket; };

static BOOL remaining_timeout(SOCKET socket_fd, int option, ULONGLONG deadline)
{
    ULONGLONG now = GetTickCount64();
    DWORD timeout;
    if (now >= deadline) return FALSE;
    timeout = (DWORD)(deadline - now);
    return !setsockopt(socket_fd, SOL_SOCKET, option, (const char *)&timeout, sizeof(timeout));
}

static BOOL send_all(SOCKET socket, const void *buffer, int bytes, ULONGLONG deadline)
{
    const char *at = buffer;
    while (bytes) {
        if (!remaining_timeout(socket, SO_SNDTIMEO, deadline)) return FALSE;
        int n = send(socket, at, bytes, 0);
        if (n <= 0) return FALSE;
        at += n;
        bytes -= n;
    }
    return TRUE;
}

static BOOL read_token(BYTE token[32])
{
    HMODULE module;
    WCHAR path[32768], *suffix;
    DWORD length, count;
    HANDLE file;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCWSTR)(void *)&db_audio_call, &module))
        return FALSE;
    length = GetModuleFileNameW(module, path, 32768);
    if (!length || length >= 32760) return FALSE;
    suffix = wcsrchr(path, L'.');
    if (!suffix || _wcsicmp(suffix, L".dll")) return FALSE;
    wcscpy(suffix, L".token");
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    BOOL ok = GetFileSize(file, NULL) == 32 && ReadFile(file, token, 32, &count, NULL) && count == 32;
    CloseHandle(file);
    return ok;
}

static BOOL receive_all(SOCKET socket_fd, void *buffer, int bytes, ULONGLONG deadline)
{
    char *at = buffer;
    while (bytes) {
        if (!remaining_timeout(socket_fd, SO_RCVTIMEO, deadline)) return FALSE;
        int n = recv(socket_fd, at, bytes, 0);
        if (n <= 0) return FALSE;
        at += n;
        bytes -= n;
    }
    return TRUE;
}

static HRESULT validate_reply(const DBReply *reply)
{
    if (memcmp(reply->magic, "DBA2", 4) || reply->count > 64 || reply->mute > 1 ||
            !isfinite(reply->volume) || reply->volume < 0 || reply->volume > 1) return E_FAIL;
    if (SUCCEEDED((HRESULT)reply->status) && !reply->count) return E_FAIL;
    for (DWORD i = 0; i < reply->count; ++i)
        if (!isfinite(reply->channels[i]) || reply->channels[i] < 0 || reply->channels[i] > 1)
            return E_FAIL;
    return (HRESULT)reply->status;
}

static HRESULT audio_open(const DBEndpointIdentity *identity, WORD operation, float value,
        LPCGUID context, DBReply *reply, DBSubscription **subscription)
{
    WSADATA data;
    SOCKET socket_fd = INVALID_SOCKET;
    DBRequest request = {{'D','B','A','2'}, operation, (WORD)identity->flow, 0, value, {0}};
    char name[4097], port_text[8];
    struct sockaddr_in address;
    ULONGLONG deadline = GetTickCount64() + RPC_DEADLINE_MS;
    u_long nonblocking = 1;
    int error = 0, error_size = sizeof(error);
    BYTE token[32], hello[36], difference = 0;
    unsigned long port = 1845;
    HRESULT hr = HRESULT_FROM_WIN32(ERROR_SERVICE_NOT_ACTIVE);
    if (!reply) return E_POINTER;
    if (context) request.context = *context;
    ZeroMemory(reply, sizeof(*reply));
    if (!read_token(token)) return E_ACCESSDENIED;
    DWORD port_length = GetEnvironmentVariableA("DECKBRIDGE_CORE_AUDIO_PORT", port_text, sizeof(port_text));
    if (port_length >= sizeof(port_text)) return E_INVALIDARG;
    if (port_length) {
        char *end;
        port = strtoul(port_text, &end, 10);
        if (*end || !port || port > 65535) return E_INVALIDARG;
    }
    int length = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, identity->name, -1,
            name, sizeof(name), NULL, NULL);
    if (!length) return E_INVALIDARG;
    request.length = (DWORD)length - 1;
    if (WSAStartup(MAKEWORD(2,2), &data)) return hr;
    socket_fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (socket_fd == INVALID_SOCKET) goto done;
    ZeroMemory(&address, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_port = htons((unsigned short)port);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (ioctlsocket(socket_fd, FIONBIO, &nonblocking)) goto done;
    if (connect(socket_fd, (struct sockaddr *)&address, sizeof(address)) == SOCKET_ERROR) {
        fd_set writes;
        struct timeval wait;
        ULONGLONG now = GetTickCount64(), remaining;
        if (WSAGetLastError() != WSAEWOULDBLOCK) goto done;
        if (now >= deadline) goto done;
        remaining = deadline - now;
        wait.tv_sec = (long)(remaining / 1000);
        wait.tv_usec = (long)(remaining % 1000) * 1000;
        FD_ZERO(&writes);
        FD_SET(socket_fd, &writes);
        if (select(0, NULL, &writes, NULL, &wait) <= 0) goto done;
        if (getsockopt(socket_fd, SOL_SOCKET, SO_ERROR, (char *)&error, &error_size) || error) goto done;
    }
    nonblocking = 0;
    if (ioctlsocket(socket_fd, FIONBIO, &nonblocking)) goto done;
    if (!receive_all(socket_fd, hello, sizeof(hello), deadline) || memcmp(hello, "DBA2", 4)) goto done;
    for (int i = 0; i < 32; ++i) difference |= token[i] ^ hello[i + 4];
    if (difference) { hr = E_ACCESSDENIED; goto done; }
    if (!send_all(socket_fd, &request, sizeof(request), deadline) ||
            !send_all(socket_fd, name, (int)request.length, deadline)) goto done;
    if (!receive_all(socket_fd, reply, sizeof(*reply), deadline)) goto done;
    hr = validate_reply(reply);
    if (SUCCEEDED(hr) && subscription) {
        *subscription = CoTaskMemAlloc(sizeof(**subscription));
        if (!*subscription) { hr = E_OUTOFMEMORY; goto done; }
        (*subscription)->socket = socket_fd;
        return hr; /* Subscription retains both socket and Winsock reference. */
    }
done:
    if (socket_fd != INVALID_SOCKET) closesocket(socket_fd);
    WSACleanup();
    return hr;
}

HRESULT db_audio_call(const DBEndpointIdentity *identity, WORD operation, float value,
        LPCGUID context, DBReply *reply)
{
    return audio_open(identity, operation, value, context, reply, NULL);
}

HRESULT db_audio_subscribe(const DBEndpointIdentity *identity, DBReply *reply, DBSubscription **result)
{
    if (!result) return E_POINTER;
    *result = NULL;
    return audio_open(identity, 3, 0, NULL, reply, result);
}

HRESULT db_audio_next(DBSubscription *subscription, HANDLE stop, DBReply *reply)
{
    SOCKET socket_fd = subscription->socket;
    while (WaitForSingleObject(stop, 0) == WAIT_TIMEOUT) {
        fd_set reads;
        struct timeval wait = {0, 250000};
        int ready;
        FD_ZERO(&reads);
        FD_SET(socket_fd, &reads);
        ready = select(0, &reads, NULL, NULL, &wait);
        if (ready == SOCKET_ERROR) return E_FAIL;
        if (!ready) continue;
        if (!receive_all(socket_fd, reply, sizeof(*reply), GetTickCount64() + RPC_DEADLINE_MS)) return E_FAIL;
        return validate_reply(reply);
    }
    return S_FALSE;
}

void db_audio_close(DBSubscription *subscription)
{
    if (!subscription) return;
    closesocket(subscription->socket);
    WSACleanup();
    CoTaskMemFree(subscription);
}
