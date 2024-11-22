{
  contentAddressableStorage: {
    backend: {
      'local': {
        keyLocationMapOnBlockDevice: {
          file: {
            path: '/cas/key_location_map',
            sizeBytes: 16 * 1024 * 1024,
          },
        },
        keyLocationMapMaximumGetAttempts: 16,
        keyLocationMapMaximumPutAttempts: 64,
        oldBlocks: 8,
        currentBlocks: 24,
        newBlocks: 3,
        blocksOnBlockDevice: {
          source: {
            file: {
              path: '/cas/blocks',
              sizeBytes: 10 * 1024 * 1024 * 1024,
            },
          },
          spareBlocks: 3,
        },
      },
    },
    getAuthorizer: { allow: {} },
    putAuthorizer: { allow: {} },
    findMissingAuthorizer: { allow: {} },
  },
  global: { diagnosticsHttpServer: {
    httpServers: [{
      listenAddresses: [':6981'],
      authenticationPolicy: { allow: {} },
    }],
  } },
  grpcServers: [{
    listenAddresses: [':7982'],
    authenticationPolicy: { allow: {} },
  }],
  maximumMessageSizeBytes: 16 * 1024 * 1024,
}
