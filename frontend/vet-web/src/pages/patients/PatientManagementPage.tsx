import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { AuthSession } from "../../api/authApi";
import { PatientDetailView } from "../../components/patients/PatientDetailView";
import { PatientListView } from "../../components/patients/PatientListView";
import { usePatientManagement } from "../../hooks/usePatientManagement";
import AppLayout, { AppMenuId } from "../../layouts/AppLayout";

interface PatientManagementPageProps {
  session: AuthSession;
  onLogout: () => void;
  onNavigate: (menuId: AppMenuId) => void;
}

export default function PatientManagementPage({
  session,
  onLogout,
  onNavigate,
}: PatientManagementPageProps) {
  const location = useLocation();
  const openedPatientIdRef = useRef<number | null>(null);
  const {
    searchValue,
    selectedSpecies,
    currentPage,
    pagePatients,
    totalCount,
    totalPages,
    isLoading,
    selectedPatient,
    selectedHistory,
    setCurrentPage,
    updateSearch,
    updateSpecies,
    handleOpenDetail,
    handleOpenDetailById,
    closeDetail,
    handleSaved,
  } = usePatientManagement(session.accessToken);

  const targetPatientId = (location.state as { patientId?: number } | null)?.patientId;

  useEffect(() => {
    if (!targetPatientId || openedPatientIdRef.current === targetPatientId) {
      return;
    }

    openedPatientIdRef.current = targetPatientId;
    handleOpenDetailById(targetPatientId);
  }, [handleOpenDetailById, targetPatientId]);

  return (
    <AppLayout
      session={session}
      activeMenu="patients"
      onLogout={onLogout}
      onNavigate={onNavigate}
    >
      {selectedPatient ? (
        <PatientDetailView
          accessToken={session.accessToken}
          patient={selectedPatient}
          history={selectedHistory}
          onBack={closeDetail}
          onSaved={handleSaved}
        />
      ) : (
        <PatientListView
          searchValue={searchValue}
          selectedSpecies={selectedSpecies}
          currentPage={currentPage}
          totalCount={totalCount}
          totalPages={totalPages}
          isLoading={isLoading}
          patients={pagePatients}
          onSearch={updateSearch}
          onChangeSpecies={updateSpecies}
          onChangePage={setCurrentPage}
          onOpenDetail={handleOpenDetail}
        />
      )}
    </AppLayout>
  );
}
