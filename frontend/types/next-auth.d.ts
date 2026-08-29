import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    /** Google ID token, forwarded to the backend as `Authorization: Bearer <token>`. */
    idToken?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    idToken?: string;
  }
}
