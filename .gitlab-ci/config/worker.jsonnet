local common = import 'common.libsonnet';

{
  blobstore: {
    contentAddressableStorage: {
      grpc: { address: 'frontend:8980' },
    },
    actionCache: {
      grpc: { address: 'frontend:8980' },
    }
  },
  maximumMessageSizeBytes: common.maximumMessageSizeBytes,
  scheduler: { address: 'scheduler:8982' },
  httpListenAddress: ':7986',
  maximumMemoryCachedDirectories: 1000,
  instanceName: '',
  buildDirectories: [{
    native: {
      buildDirectoryPath: '/worker/build',
      cacheDirectoryPath: '/worker/cache',
      maximumCacheFileCount: 10000,
      maximumCacheSizeBytes: 5 * 1024 * 1024 * 1024,
      cacheReplacementPolicy: 'LEAST_RECENTLY_USED',
    },
    runners: [{
      endpoint: { address: 'unix:///worker/runner' },
      concurrency: 8,
      platform: {
        properties: [{ name: "ISA" , value:"x86-64"}, { name:"OSFamily", value:"linux"}],
      },
      defaultExecutionTimeout: '1800s',
      maximumExecutionTimeout: '3600s',
      workerId: {
      },
    }],
  }],
}