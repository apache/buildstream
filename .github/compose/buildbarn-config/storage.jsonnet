{
  blobstore: {
    contentAddressableStorage: {
      circular: {
        directory: '/cas',
        offsetFileSizeBytes: 16 * 1024 * 1024,
        offsetCacheSize: 10000,
        dataFileSizeBytes: 10 * 1024 * 1024 * 1024,
        dataAllocationChunkSizeBytes: 16 * 1024 * 1024,
      },
    },
    actionCache: {
      'error': {
          code: 12, # UNIMPLEMENTED
          message: "AC requests are not supported for this endpoint.",
        }
    },
  },
  httpListenAddress: ':6981',
  grpcServers: [{
    listenAddresses: [':7982'],
    authenticationPolicy: { allow: {} },
  }],
  allowAcUpdatesForInstanceNamePrefixes: [''],
  maximumMessageSizeBytes: 16 * 1024 * 1024,
}
