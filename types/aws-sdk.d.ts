declare module '@aws-sdk/client-s3' {
  export class S3Client {
    constructor(config: Record<string, unknown>);
    send<T>(command: unknown): Promise<T>;
  }

  export class CreateMultipartUploadCommand {
    constructor(input: Record<string, unknown>);
  }

  export class UploadPartCommand {
    constructor(input: Record<string, unknown>);
  }

  export class PutObjectCommand {
    constructor(input: Record<string, unknown>);
  }

  export class CompleteMultipartUploadCommand {
    constructor(input: Record<string, unknown>);
  }

  export class GetObjectCommand {
    constructor(input: Record<string, unknown>);
  }

  export class HeadObjectCommand {
    constructor(input: Record<string, unknown>);
  }
}

declare module '@aws-sdk/s3-request-presigner' {
  export function getSignedUrl(
    client: unknown,
    command: unknown,
    options: Record<string, unknown>
  ): Promise<string>;
}
