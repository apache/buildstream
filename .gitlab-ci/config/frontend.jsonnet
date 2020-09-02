local common = import 'common.libsonnet';

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
      circular: {
        directory: '/ac',
        offsetFileSizeBytes: 1024 * 1024,
        offsetCacheSize: 1000,
        dataFileSizeBytes: 100 * 1024 * 1024,
        dataAllocationChunkSizeBytes: 1048576,
        instances: [''],
      },
    },
  },
  httpListenAddress: ':7980',
  grpcServers: [{
    listenAddresses: [':8980'],
    authenticationPolicy: { allow: {} },
  }],
  schedulers: {
    '': { endpoint: { address: 'scheduler:8981'} },
  },
  allowAcUpdatesForInstanceNamePrefixes: [''],
  maximumMessageSizeBytes: common.maximumMessageSizeBytes,
}
