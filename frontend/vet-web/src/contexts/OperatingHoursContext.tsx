import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { fetchOperatingHours } from "../api/settingsApi";
import { AuthSession } from "../api/authApi";

interface OperatingHoursValue {
  startTime: string;
  endTime: string;
  lunchStart: string;
  lunchEnd: string;
}

const defaultHours: OperatingHoursValue = {
  startTime: "09:00",
  endTime: "18:00",
  lunchStart: "12:00",
  lunchEnd: "13:00",
};

const OperatingHoursContext = createContext<OperatingHoursValue>(defaultHours);

export function OperatingHoursProvider({
  session,
  children,
}: {
  session: AuthSession;
  children: ReactNode;
}) {
  const [hours, setHours] = useState<OperatingHoursValue>(defaultHours);

  useEffect(() => {
    fetchOperatingHours(session.accessToken)
      .then((data) =>
        setHours({
          startTime: data.start_time,
          endTime: data.end_time,
          lunchStart: data.lunch_start,
          lunchEnd: data.lunch_end,
        })
      )
      .catch(() => {});
  }, [session.accessToken]);

  return (
    <OperatingHoursContext.Provider value={hours}>
      {children}
    </OperatingHoursContext.Provider>
  );
}

export function useOperatingHours() {
  return useContext(OperatingHoursContext);
}
