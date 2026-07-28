import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { appRoutes } from './appRoutes';
import AppShell from './components/layout/AppShell';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          {appRoutes.map((route) => (
            <Route key={route.path} path={route.path} element={route.element} />
          ))}
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
