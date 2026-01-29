import React, { useState, useEffect } from "react";

function App() {
  // steps: 1 intro, 2 demand, 3 candidate, 4 model, 5 map
  const [step, setStep] = useState(1);

  // scenario name from intro
  const [scenarioName, setScenarioName] = useState("");
  const [userEmail, setUserEmail] = useState("");
  // form states
  const [demandMetric, setDemandMetric] = useState("");
  const [candidateSites, setCandidateSites] = useState({
    elementary: false,
    middle: false,
    high: false,
    libraries: false,
  });
  const [model, setModel] = useState("pmedian");
  const [pValue, setPValue] = useState(5);
  const [coverage, setCoverage] = useState(5);
  const [notifyEmail, setNotifyEmail] = useState(true);

  const [availableScenarios] = useState([
    "fall25_cs_teacher_access",
    "atlanta_libraries",
    "rural_coverage_test",
  ]);

  const [analysisLink, setAnalysisLink] = useState("");
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);

  const canGoNext =
    (step === 1 && scenarioName.trim() !== "" && userEmail.trim() !== "") ||
    (step === 2 && demandMetric) ||
    step === 3 ||
    step === 4 ||
    step === 5;


  const handleNext = () => {
    if (step < 5) setStep(step + 1);
  };

  const handleBack = () => {
    if (step > 1) setStep(step - 1);
  };

const handleRunAnalysis = async () => {
  try {
    const res = await fetch("/api/scenarios/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenarioName,
        email: userEmail,
        demandMetric,
        candidateSites,
        model,
        p: pValue,
        coverageMiles: coverage,
        notifyEmail: true, // always email
      }),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    const jobId = data.job_id;

    setJobId(jobId);
    setJobStatus("running");

    setStep(6);

    const pollInterval = setInterval(async () => {
      try {
        const statusRes = await fetch(`/api/jobs/${jobId}`);
        if (statusRes.ok) {
          const statusData = await statusRes.json();
          setJobStatus(statusData.status);

          if (statusData.status === "completed") {
            setAnalysisLink(statusData.results_url);
            clearInterval(pollInterval);
          } else if (statusData.status === "failed") {
            clearInterval(pollInterval);
          }
        }
      } catch (err) {
        clearInterval(pollInterval);
      }
    }, 3000);

  } catch (err) {
    alert("Failed to start analysis");
  }
};


  return (
    <div className="min-h-screen bg-slate-100 flex flex-col items-center py-8">
      <div className="w-full max-w-6xl bg-white rounded-xl shadow p-6">
        <Header step={step} onStepChange={setStep} />
        <div className="mt-6 grid grid-cols-1 lg:grid-cols-[1.2fr_0.8fr] gap-6">
          <div>
            {step === 1 && (
  <Step0
    scenarioName={scenarioName}
    setScenarioName={setScenarioName}
    userEmail={userEmail}
    setUserEmail={setUserEmail}
  />
)}

            {step === 2 && (
              <Step1
                demandMetric={demandMetric}
                setDemandMetric={setDemandMetric}
              />
            )}
            {step === 3 && (
              <Step2
                candidateSites={candidateSites}
                setCandidateSites={setCandidateSites}
              />
            )}
            {step === 4 && (
              <Step3
                model={model}
                setModel={setModel}
                pValue={pValue}
                setPValue={setPValue}
                coverage={coverage}
                setCoverage={setCoverage}
              />
            )}
          {step === 5 && (
  <Step4
    scenarioName={scenarioName}
    demandMetric={demandMetric}
    candidateSites={candidateSites}
    model={model}
    pValue={pValue}
    coverage={coverage}
    availableScenarios={availableScenarios}
    analysisLink={analysisLink}
    notifyEmail={notifyEmail}
    setNotifyEmail={setNotifyEmail}
    userEmail={userEmail}      
    onRun={handleRunAnalysis}
  />
)}

          </div>
          <RightPanel
            step={step}
            model={model}
            candidateSites={candidateSites}
          />
        </div>
<div className="mt-6 flex justify-between">
  <button
    onClick={handleBack}
    disabled={step === 1}
    className={`px-4 py-2 rounded ${
      step === 1
        ? "bg-slate-200 text-slate-500 cursor-not-allowed"
        : "bg-slate-700 text-white"
    }`}
  >
    Back
  </button>

  {step < 5 && (
    <button
      onClick={handleNext}
      disabled={!canGoNext}
      className={`px-4 py-2 rounded ${
        !canGoNext
          ? "bg-slate-200 text-slate-500 cursor-not-allowed"
          : "bg-emerald-600 text-white"
      }`}
    >
      Next
    </button>
  )}
  {step === 6 && (
  <AnalysisRunningScreen
    userEmail={userEmail}
    jobStatus={jobStatus}
    analysisLink={analysisLink}
  />
)}

</div>


      </div>
    </div>
  );
}

function Header({ step, onStepChange }) {
  const steps = [
    "Introduction",
    "Select demand",
    "Select candidate sites",
    "Select model & params",
    "Scenario summary & run",  
  ];

  return (
    <div className="flex items-center gap-4">
      {steps.map((label, idx) => {
        const thisStep = idx + 1;
        const current = thisStep === step;
        const done = thisStep < step;

        return (
          <div key={label} className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onStepChange(thisStep)}
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold border transition 
                ${
                  current
                    ? "bg-emerald-500 text-white border-emerald-500"
                    : done
                    ? "bg-emerald-100 text-emerald-700 border-emerald-200"
                    : "bg-slate-200 text-slate-500 border-slate-200"
                }`}
            >
              {thisStep}
            </button>
            <span
              className={`text-sm ${
                current ? "text-slate-900 font-medium" : "text-slate-500"
              }`}
            >
              {label}
            </span>
            {idx !== steps.length - 1 && (
              <div className="w-8 h-px bg-slate-200" />
            )}
          </div>
        );
      })}
    </div>
  );
}

function RightPanel({ step, model, candidateSites }) {
  if (step === 1) {
    return (
      <div className="border rounded-lg bg-slate-50 p-4">
        <p className="text-xs text-slate-600 mt-2">
         Welcome!
This web application helps users identify the best possible locations for setting up facilities—like schools, libraries, or service centers—based on demand and coverage metrics.
You can create scenarios, explore demand data, choose candidate sites, and run spatial optimization models such as P-Median or Location Set Covering (LSCP).
Once the analysis is complete, the platform generates interactive maps and reports, making it easier to visualize results and compare solutions.

In short, this tool brings together data analytics, GIS visualization, and optimization algorithms to support smarter, data-driven decisions.
        </p>
        <p className="text-xs text-slate-500 mt-3">
          Example: <em>“atlanta_public_libraries_5mile_coverage”</em>
        </p>
      </div>
    );
  }

  if (step === 2) {
    return (
      <div className="border rounded-lg bg-slate-50 p-4">
        <h3 className="text-sm font-semibold text-slate-800">
          About demand metrics
        </h3>
        <p className="text-xs text-slate-600 mt-2">
          Demand metrics define “need.” These can be student:faculty ratios,
          representation-index-weighted demand, or a custom weighted metric.
        </p>
        <p className="text-xs text-slate-600 mt-2">
          The chosen metric will be used to rank schools / block groups before
          the optimization step.
        </p>
      </div>
    );
  }

  if (step === 3) {
    const selected = Object.entries(candidateSites)
      .filter(([, v]) => v)
      .map(([k]) => k);
    return (
      <div className="border rounded-lg bg-slate-50 p-4">
        <h3 className="text-sm font-semibold text-slate-800">
          What are candidate sites?
        </h3>
        <p className="text-xs text-slate-600 mt-2">
          Candidate sites are locations the model is allowed to choose from.
          These might be existing schools, public libraries, community centers,
          etc.
        </p>
        <p className="text-xs text-slate-600 mt-2">
          The model will open a subset of these based on your objective.
        </p>
        <p className="text-xs text-slate-500 mt-3">
          Selected now: {selected.length > 0 ? selected.join(", ") : "none"}
        </p>
        <p className="text-xs text-slate-400 mt-2">
          (Later we can show counts, e.g. Elementary (124), Libraries (38) —
          from DB.)
        </p>
      </div>
    );
  }

  if (step === 4) {
    return (
      <div className="border rounded-lg bg-slate-50 p-4">
        <h3 className="text-sm font-semibold text-slate-800">
          Model help: {model}
        </h3>
        {model === "pmedian" && (
          <p className="text-xs text-slate-600 mt-2">
            P-Median minimizes total distance. You must choose <strong>p</strong>{" "}
            (how many sites to open). Coverage distance is optional here — we
            can still show it for stats.
          </p>
        )}
        {model === "lscp" && (
          <p className="text-xs text-slate-600 mt-2">
            Location Set Covering ensures every demand point is within the
            coverage distance. If infeasible, increase coverage or allow more
            sites.
          </p>
        )}
        {model === "mclp" && (
          <p className="text-xs text-slate-600 mt-2">
            Maximal Coverage tries to cover as much demand as possible with
            fixed p and coverage distance.
          </p>
        )}
        <p className="text-xs text-slate-400 mt-3">
          “Spider map” on the next screen will show lines from facilities to
          assigned demand points.
        </p>
      </div>
    );
  }

if (step === 5) {
  return (
    <div className="border rounded-lg bg-slate-50 p-4">
      <h3 className="text-sm font-semibold text-slate-800">
        Scenario summary & run
      </h3>
      <p className="text-xs text-slate-600 mt-2">
        Review your scenario settings (demand, candidate sites, model and
        parameters), then run the optimization.
      </p>
      <p className="text-xs text-slate-600 mt-2">
        When you click <strong>Save &amp; run analysis</strong>, the system will
        store this scenario in the database, trigger the optimization model,
        and (optionally) email you a link when it’s finished.
      </p>
    </div>
  );
}


  return null;
}

function Step0({ scenarioName, setScenarioName, userEmail, setUserEmail }) {
  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-900 mb-2">
        Location Modeling Scenario Setup
      </h2>
      <p className="text-slate-600 mb-4">
        Create a scenario to organize your inputs and save results to the
        database.
      </p>

      <label className="block text-sm font-medium text-slate-700 mb-1">
        Scenario name
      </label>
      <input
        value={scenarioName}
        onChange={(e) => setScenarioName(e.target.value)}
        placeholder="e.g. atlanta_cs_libraries_fall25"
        className="w-full border rounded-lg px-3 py-2"
      />
      <p className="text-xs text-slate-500 mt-1">
        This name will be used as part of the schema/table name in the
        database.
      </p>

      <label className="block text-sm font-medium text-slate-700 mt-4 mb-1">
        Notification email
      </label>
      <input
        type="email"
        value={userEmail}
        onChange={(e) => setUserEmail(e.target.value)}
        placeholder="you@example.edu"
        className="w-full border rounded-lg px-3 py-2"
      />
      <p className="text-xs text-slate-500 mt-1">
        We’ll send a link here when the analysis finishes.
      </p>
    </div>
  );
}

function Step1({ demandMetric, setDemandMetric }) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-900">
        2. Select demand metric
      </h2>
      <p className="text-sm text-slate-500 mt-1">
        This defines how we measure “need”.
      </p>

      <div className="mt-4">
        <label className="block text-sm font-medium text-slate-700">
          Demand metric
        </label>
        <select
          value={demandMetric}
          onChange={(e) => setDemandMetric(e.target.value)}
          className="mt-1 w-full border rounded-lg px-3 py-2"
        >
          <option value="">Select a demand metric</option>
          <option value="sfr">Student-Faculty ratio</option>
          <option value="cs_enrollment">
            Student count
          </option>
          <option value="certified_teachers">
            Teacher Count
          </option>
        </select>
      </div>
    </div>
  );
}

function Step2({ candidateSites, setCandidateSites }) {
  const [siteCounts, setSiteCounts] = useState({
    elementary: 124,
    middle: 59,
    high: 41,
    libraries: 37,
  });
  useEffect(() => {
    const fetchSiteCounts = async () => {
      try {
        const res = await fetch("/api/candidate-sites");
        if (res.ok) {
          const data = await res.json();
          if (data.status === "ok") {
            setSiteCounts(data.sites);
          }
        }
      } catch (err) {
        console.error("Failed to fetch site counts:", err);
      }
    };
    fetchSiteCounts();
  }, []);

  const toggle = (key) => {
    setCandidateSites((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-900">
        3. Select candidate sites
      </h2>
      <p className="text-sm text-slate-500 mt-1">
        Choose which facility types the model can open.
      </p>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={candidateSites.elementary}
            onChange={() => toggle("elementary")}
          />
          <span>Elementary schools ({siteCounts.elementary})</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={candidateSites.middle}
            onChange={() => toggle("middle")}
          />
          <span>Middle schools ({siteCounts.middle})</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={candidateSites.high}
            onChange={() => toggle("high")}
          />
          <span>High schools ({siteCounts.high})</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={candidateSites.libraries}
            onChange={() => toggle("libraries")}
          />
          <span>Public libraries ({siteCounts.libraries})</span>
        </label>
      </div>
    </div>
  );
}

function Step3({
  model,
  setModel,
  pValue,
  setPValue,
  coverage,
  setCoverage,
}) {
  const showP = model === "pmedian" || model === "mclp";
  const showCoverage = true;

  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-900">
        4. Select model & parameters
      </h2>
      <p className="text-sm text-slate-500 mt-1">
        Pick the optimization objective.
      </p>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700">
            Model
          </label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="mt-1 w-full border rounded-lg px-3 py-2"
          >
            <option value="pmedian">P-Median (minimize distance)</option>
            <option value="lscp">Location Set Covering</option>
            <option value="mclp">Maximal Coverage</option>
          </select>
        </div>

        {showP && (
          <div>
            <label className="block text-sm font-medium text-slate-700">
              p (number of facilities)
            </label>
            <input
              type="number"
              min="1"
              value={pValue}
              onChange={(e) => setPValue(Number(e.target.value))}
              className="mt-1 w-full border rounded-lg px-3 py-2"
            />
            <p className="text-xs text-slate-400 mt-1">
              e.g. 5 = open 5 sites
            </p>
          </div>
        )}

        {showCoverage && (
          <div>
            <label className="block text-sm font-medium text-slate-700">
              Coverage distance (miles)
            </label>
            <input
              type="number"
              min="1"
              value={coverage}
              onChange={(e) => setCoverage(Number(e.target.value))}
              className="mt-1 w-full border rounded-lg px-3 py-2"
            />
            <p className="text-xs text-slate-400 mt-1">
              Demand within this distance is covered
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function Step4({
  scenarioName,
  demandMetric,
  candidateSites,
  model,
  pValue,
  coverage,
  availableScenarios,
  analysisLink,
  notifyEmail,
  setNotifyEmail,
  userEmail,
  onRun,
}) {
  const selectedCandidates = Object.entries(candidateSites)
    .filter(([, v]) => v)
    .map(([k]) => k)
    .join(", ");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-4 items-center">
        <div>
          <label className="block text-sm font-medium text-slate-700">
            Load scenario
          </label>
          <select className="mt-1 border rounded-lg px-3 py-2">
            <option value="">Current ({scenarioName || "unnamed"})</option>
            {availableScenarios.map((sc) => (
              <option key={sc} value={sc}>
                {sc}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={onRun}
          className="mt-6 md:mt-7 px-4 py-2 rounded bg-emerald-600 text-white"
        >
          Save &amp; run analysis
        </button>
      </div>
      <div className="border rounded-lg bg-slate-50 p-4">
        <h3 className="text-md font-semibold text-slate-900">
          Scenario summary
        </h3>
        <ul className="mt-3 space-y-2 text-sm">
          <li>
            <span className="font-medium">Scenario:</span>{" "}
            {scenarioName || "—"}
          </li>
          <li>
            <span className="font-medium">Notification email:</span>{" "}
            {userEmail || "—"}
          </li>
          <li>
            <span className="font-medium">Demand metric:</span>{" "}
            {demandMetric || "—"}
          </li>
          <li>
            <span className="font-medium">Candidate sites:</span>{" "}
            {selectedCandidates || "None selected"}
          </li>
          <li>
            <span className="font-medium">Model:</span> {model}
          </li>
          <li>
            <span className="font-medium">p:</span>{" "}
            {model === "pmedian" || model === "mclp" ? pValue : "—"}
          </li>
          <li>
            <span className="font-medium">Coverage:</span> {coverage} miles
          </li>
        </ul>

        <div className="mt-4">
          <h4 className="text-sm font-semibold text-slate-800">
            Analysis status
          </h4>
          {!analysisLink ? (
            <p className="text-xs text-slate-500 mt-1">
              Click “Save &amp; run analysis” to start. You will get a link
              here. Email notification is{" "}
              {notifyEmail ? "ON" : "OFF"}.
            </p>
          ) : (
            <p className="text-xs text-emerald-600 mt-1 break-all">
              Analysis complete. View results: {analysisLink}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function AnalysisRunningScreen({ userEmail, jobStatus, analysisLink }) {
  return (
    <div className="max-w-xl mx-auto text-center space-y-6">
      <div className="text-3xl">📊</div>

      <h2 className="text-2xl font-semibold text-slate-900">
        Analysis is running
      </h2>

      <p className="text-slate-600">
        Your scenario has been successfully submitted.
      </p>

      <div className="border rounded-lg bg-slate-50 p-4">
        <p className="text-sm text-slate-700">
          📧 <strong>Results will be sent to:</strong>
        </p>
        <p className="text-sm text-emerald-600 mt-1">
          {userEmail}
        </p>
      </div>

      <p className="text-sm text-slate-500">
        You can safely close this page.  
        The analysis will continue running in the background.
      </p>

      {jobStatus === "running" && (
        <p className="text-sm text-blue-600">
          ⏳ Currently running optimization models…
        </p>
      )}

      {jobStatus === "completed" && analysisLink && (
        <p className="text-sm text-emerald-700 break-all">
          Analysis complete. Results link: {analysisLink}
        </p>
      )}

      {jobStatus === "failed" && (
        <p className="text-sm text-red-600">
          Analysis failed. Please try again or contact support.
        </p>
      )}
    </div>
  );
}

export default App;
