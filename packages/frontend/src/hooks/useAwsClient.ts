import { useCallback, useRef } from 'react';
import { useAuth } from 'react-oidc-context';
import { fromCognitoIdentityPool } from '@aws-sdk/credential-providers';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { AwsClient } from 'aws4fetch';
import { useRuntimeConfig } from './useRuntimeConfig';

const REFRESH_BUFFER_MS = 5 * 60 * 1000; // 5분 전에 갱신

interface Credentials {
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken?: string;
  expiration?: Date;
}

export function useAwsClient() {
  const { apis, cognitoProps, documentStorageBucketName } = useRuntimeConfig();
  const { user } = useAuth();
  const credentialsRef = useRef<Credentials | null>(null);

  const getCredentials = useCallback(async (): Promise<Credentials> => {
    if (!cognitoProps || !user?.id_token) {
      throw new Error('Cognito props or user token not available');
    }

    const now = Date.now();
    const cached = credentialsRef.current;

    if (
      cached?.expiration &&
      cached.expiration.getTime() - now > REFRESH_BUFFER_MS
    ) {
      return cached;
    }

    const credentials = await fromCognitoIdentityPool({
      clientConfig: { region: cognitoProps.region },
      identityPoolId: cognitoProps.identityPoolId,
      logins: {
        [`cognito-idp.${cognitoProps.region}.amazonaws.com/${cognitoProps.userPoolId}`]:
          user.id_token,
      },
    })();
    credentialsRef.current = credentials;
    return credentials;
  }, [cognitoProps, user]);

  const fetchApi = useCallback(
    async <T>(path: string, options?: RequestInit): Promise<T> => {
      if (!cognitoProps) {
        throw new Error('Cognito props not available');
      }
      if (!apis?.Backend) {
        throw new Error('Backend API URL not available');
      }

      const credentials = await getCredentials();

      const client = new AwsClient({
        accessKeyId: credentials.accessKeyId,
        secretAccessKey: credentials.secretAccessKey,
        sessionToken: credentials.sessionToken,
        region: cognitoProps.region,
        service: 'execute-api',
      });

      const response = await client.fetch(`${apis.Backend}${path}`, options);

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      return response.json();
    },
    [apis, cognitoProps, getCredentials],
  );

  const uploadToS3 = useCallback(
    async (file: File, key: string): Promise<void> => {
      if (!cognitoProps) {
        throw new Error('Cognito props not available');
      }
      if (!documentStorageBucketName) {
        throw new Error('Document storage bucket name not available');
      }

      const credentials = await getCredentials();

      const s3Client = new S3Client({
        region: cognitoProps.region,
        credentials: {
          accessKeyId: credentials.accessKeyId,
          secretAccessKey: credentials.secretAccessKey,
          sessionToken: credentials.sessionToken,
        },
      });

      const arrayBuffer = await file.arrayBuffer();

      await s3Client.send(
        new PutObjectCommand({
          Bucket: documentStorageBucketName,
          Key: key,
          Body: new Uint8Array(arrayBuffer),
          ContentType: file.type,
        }),
      );
    },
    [cognitoProps, documentStorageBucketName, getCredentials],
  );

  return { fetchApi, uploadToS3 };
}
