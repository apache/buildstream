{
  blobstore: {
    contentAddressableStorage: {
      grpc: { address: 'frontend:8980' },
    },
    actionCache: {
      grpc: { address: 'frontend:8980' },
    },
  },
  httpListenAddress: ':80',
  maximumMessageSizeBytes: 16 * 1024 * 1024,
}