{
  contentAddressableStorage: {
    grpc: {
      address: 'localhost:7982',
    },
  },
  fetcher: {
    // We should never be fetching anything which is not already returned by the caching fetcher.
    'error': {
      code: 5,
      message: "Asset Not Found",
    }
  },
  assetCache: {
    blobAccess: {
      'local': {
        keyLocationMapOnBlockDevice: {
          file: {
            path: '/storage/key_location_map',
            sizeBytes: 1024 * 1024,
          },
        },
        keyLocationMapMaximumGetAttempts: 8,
        keyLocationMapMaximumPutAttempts: 32,
        oldBlocks: 8,
        currentBlocks: 24,
        newBlocks: 1,
        blocksOnBlockDevice: {
          source: {
            file: {
              path: '/storage/blocks',
              sizeBytes: 100 * 1024 * 1024,
            },
          },
          spareBlocks: 3,
        },
      },
    },
  },
  grpcServers: [{
    listenAddresses: [':7981'],
    authenticationPolicy: { allow: {} },
  }],
  allowUpdatesForInstances: [''],
  maximumMessageSizeBytes: 16 * 1024 * 1024,
  fetchAuthorizer: { allow: {} },
  pushAuthorizer: { allow: {} },
}

