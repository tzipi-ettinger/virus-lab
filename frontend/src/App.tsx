// App shell. Only layout: the review screen owns its own state (#32). Routes,
// login and navigation come with the frontend shell (B1.6).
// Owner: shared

import "./shared/ui/tokens.css";
import { ReviewPage } from "./features/review/ReviewPage";

function App() {
  return (
    <main>
      <h1>מטפסי התחייבות לנתונים מובנים</h1>
      <ReviewPage />
    </main>
  )
}

export default App
