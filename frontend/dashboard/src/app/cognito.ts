import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserAttribute,
  CognitoUserPool,
  ISignUpResult,
} from "amazon-cognito-identity-js";

type Tokens = {
  idToken: string;
  accessToken: string;
  refreshToken?: string;
  email: string;
};

const clientId = String(import.meta.env.VITE_COGNITO_CLIENT_ID ?? "").trim();
const configuredUserPoolId = String(import.meta.env.VITE_COGNITO_USER_POOL_ID ?? "").trim();
const authority = String(import.meta.env.VITE_COGNITO_AUTHORITY ?? "").trim();

function inferUserPoolId(value: string): string {
  const m = value.match(/([a-z]{2}-[a-z]+-\d+_[A-Za-z0-9]+)/);
  return m ? m[1] : "";
}

const userPoolId = configuredUserPoolId || inferUserPoolId(authority);

if (!clientId || !userPoolId) {
  throw new Error("Missing Cognito config. Set VITE_COGNITO_CLIENT_ID and VITE_COGNITO_USER_POOL_ID (or authority with pool id).");
}

const pool = new CognitoUserPool({
  UserPoolId: userPoolId,
  ClientId: clientId,
});

function toTokens(user: CognitoUser, session: any): Tokens {
  const idToken = String(session?.getIdToken()?.getJwtToken?.() ?? "");
  const accessToken = String(session?.getAccessToken()?.getJwtToken?.() ?? "");
  const refreshToken = String(session?.getRefreshToken()?.getToken?.() ?? "");
  const attrs = session?.getIdToken()?.decodePayload?.() ?? {};
  const email = String(attrs.email ?? user.getUsername() ?? "").trim();
  return { idToken, accessToken, refreshToken, email };
}

export function cognitoLogin(email: string, password: string): Promise<Tokens> {
  const user = new CognitoUser({ Username: email.trim(), Pool: pool });
  const details = new AuthenticationDetails({
    Username: email.trim(),
    Password: password,
  });
  return new Promise((resolve, reject) => {
    user.authenticateUser(details, {
      onSuccess: (session) => resolve(toTokens(user, session)),
      onFailure: (err) => reject(err),
      newPasswordRequired: () => reject(new Error("New password challenge is not supported in this UI.")),
    });
  });
}

export function cognitoSignup(email: string, password: string): Promise<ISignUpResult> {
  const attributes = [new CognitoUserAttribute({ Name: "email", Value: email.trim() })];
  return new Promise((resolve, reject) => {
    pool.signUp(email.trim(), password, attributes, [], (err, result) => {
      if (err || !result) {
        reject(err ?? new Error("Signup failed"));
        return;
      }
      resolve(result);
    });
  });
}

export function cognitoConfirmSignup(email: string, code: string): Promise<void> {
  const user = new CognitoUser({ Username: email.trim(), Pool: pool });
  return new Promise((resolve, reject) => {
    user.confirmRegistration(code.trim(), true, (err) => {
      if (err) {
        reject(err);
        return;
      }
      resolve();
    });
  });
}

export function cognitoResendSignupCode(email: string): Promise<void> {
  const user = new CognitoUser({ Username: email.trim(), Pool: pool });
  return new Promise((resolve, reject) => {
    user.resendConfirmationCode((err) => {
      if (err) {
        reject(err);
        return;
      }
      resolve();
    });
  });
}

export function cognitoRestoreSession(): Promise<Tokens | null> {
  const user = pool.getCurrentUser();
  if (!user) {
    return Promise.resolve(null);
  }
  return new Promise((resolve, reject) => {
    user.getSession((err, session) => {
      if (err || !session || !session.isValid()) {
        resolve(null);
        return;
      }
      resolve(toTokens(user, session));
    });
  });
}

export function cognitoSignOut(): void {
  const user = pool.getCurrentUser();
  if (user) {
    user.signOut();
  }
}
