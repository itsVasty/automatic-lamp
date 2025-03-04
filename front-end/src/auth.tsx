import { GoogleLogin } from "@react-oauth/google";
import { createContext, useState } from "react";
import { useLocalStorage } from "./localstorage";
import { jwtDecode } from "jwt-decode";

export let googleContext: any = createContext(null);

export function GoogleLoginGate({ children }: { children: React.ReactNode }) {
    const [token, setToken] = useLocalStorage('token', '');

    const handleSuccess = (CredentialResponse: any) => {
        const credential = CredentialResponse.credential
        setToken(jwtDecode(credential))
    }
    
    const handleFailure = () => {
        console.log(`Signin Failed`)
    }
    
    if (token === '' || null) {
        return (
            // @ts-ignore
            <GoogleLogin onSuccess={handleSuccess} onError={handleFailure}/> 
        );
    }

    return (
        <googleContext.Provider value={{
            token,
            signOut: () => {
                setToken('')
            }
        }}>
            {children}
        </googleContext.Provider>
    );
}