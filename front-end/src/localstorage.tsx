import { useState, useEffect } from "react";

function getStorageValue(key : any, defaultValue : any) {
  // getting stored value
  const value : any = localStorage.getItem(key);
  const initial = JSON.parse(value);
  return initial || defaultValue;
}

export const useLocalStorage = (key : any, defaultValue : any) => {
  const [value, setValue] = useState(() => {
    return getStorageValue(key, defaultValue)
  })

  useEffect(() => {
    // storing input name
    localStorage.setItem(key, JSON.stringify(value))
  }, [key, value])

  return [value, setValue]
}