import Project from "../models/project";
import Settings from "../models/settings";
import httpService from "./httpService";
import config from "../config.json";
import Source from "../models/source";
import Prep from "../models/prep";
import PrepRound from "../models/prepRound";
import Dedupe from "../models/dedupe";
import Prescreen from "../models/prescreen";
import Data from "../models/data";
import PdfGet from "../models/pdfGet";
import PdfPrep from "../models/pdfPrep";
import Screen from "../models/screen";
import Search from "../models/search";
import ScriptParameterType from "../models/scriptParameterType";
import ScriptParameterDefinition from "../models/scriptParameterDefinition";
import Script from "../models/script";
import ScriptDefinition from "../models/scriptDefinition";

const apiEndpoint = config.apiEndpoint + "/api";

let settingsFile: any = {};

const getSettings = async (): Promise<Settings> => {
  const response = await httpService.get(`${apiEndpoint}/getSettings`);

  settingsFile = response.data;

  const settings = new Settings();

  settings.project = new Project();
  projectFromSettings(settings.project, settingsFile.project);

  for (const s of settingsFile.sources) {
    const source = new Source();
    sourceFromSettings(source, s);
    settings.sources.push(source);
  }

  settings.search = new Search();
  searchFromSettings(settings.search, settingsFile.search);

  settings.prep = new Prep();
  prepFromSettings(settings.prep, settingsFile.prep);

  settings.dedupe = new Dedupe();
  dedupeFromSettings(settings.dedupe, settingsFile.dedupe);

  settings.prescreen = new Prescreen();
  prescreenFromSettings(settings.prescreen, settingsFile.prescreen);

  settings.pdfGet = new PdfGet();
  pdfGetFromSettings(settings.pdfGet, settingsFile.pdf_get);

  settings.pdfPrep = new PdfPrep();
  pdfPrepFromSettings(settings.pdfPrep, settingsFile.pdf_prep);

  settings.screen = new Screen();
  screenFromSettings(settings.screen, settingsFile.screen);

  settings.data = new Data();
  dataFromSettings(settings.data, settingsFile.data);

  return Promise.resolve<Settings>(settings);
};

const saveSettings = async (settings: Settings): Promise<void> => {
  const newSettingsFile = {
    ...settingsFile,
    project: projectToSettings(settings.project),
    sources: [],
    search: searchToSettings(settings.search),
    prep: prepToSettings(settings.prep),
    dedupe: dedupeToSettings(settings.dedupe),
    prescreen: prescreenToSettings(settings.prescreen),
    pdf_get: pdfGetToSettings(settings.pdfGet),
    pdf_prep: pdfPrepToSettings(settings.pdfPrep),
    screen: screenToSettings(settings.screen),
    data: dataToSettings(settings.data),
  };

  for (const source of settings.sources) {
    const settingsFileSource = sourceToSettings(source);
    newSettingsFile.sources.push(settingsFileSource);
  }

  await httpService.post(`${apiEndpoint}/saveSettings`, newSettingsFile, {
    headers: { "content-type": "application/json" },
  });

  return Promise.resolve();
};

const projectFromSettings = (project: Project, settingsProject: any) => {
  project.title = settingsProject.title;
  project.authors = settingsProject.authors;
  project.keywords = settingsProject.keywords;
  project.protocol = settingsProject.protocol;
  project.reviewType = settingsProject.review_type;
  project.idPattern = settingsProject.id_pattern;
  project.shareStatReq = settingsProject.share_stat_req;
  project.delayAutomatedProcessing = settingsProject.delay_automated_processing;
  project.curationUrl = settingsProject.curation_url;
  project.curatedMasterdata = settingsProject.curated_masterdata;
  project.curatedFields = settingsProject.curated_fields;
  project.colrevVersion = settingsProject.colrev_version;
};

const projectToSettings = (project: Project): any => {
  const settingsFileProject = {
    ...settingsFile.project,
    title: project.title,
    authors: project.authors,
    keywords: project.keywords,
    protocol: project.protocol,
    review_type: project.reviewType,
    id_pattern: project.idPattern,
    share_stat_req: project.shareStatReq,
    delay_automated_processing: project.delayAutomatedProcessing,
    curation_url: project.curationUrl,
    curated_masterdata: project.curatedMasterdata,
    curated_fields: project.curatedFields,
  };
  return settingsFileProject;
};

const sourceFromSettings = (source: Source, settingsSource: any) => {
  source.filename = settingsSource.filename;
  source.searchType = settingsSource.search_type;
  source.sourceName = settingsSource.source_name;
  source.sourceIdentifier = settingsSource.source_identifier;

  source.searchParameters = settingsSource.search_parameters;

  source.loadConversionScript.endpoint =
    settingsSource.load_conversion_script.endpoint;

  source.comment = settingsSource.comment;
};

const sourceToSettings = (source: Source): any => {
  const settingsFileSource = {
    filename: source.filename,
    search_type: source.searchType,
    source_name: source.sourceName,
    source_identifier: source.sourceIdentifier,

    search_parameters: source.searchParameters,

    load_conversion_script: {
      endpoint: source.loadConversionScript.endpoint,
    },

    comment: source.comment,
  };

  return settingsFileSource;
};

const searchFromSettings = (search: Search, settingsSearch: any) => {
  search.retrieveForthcoming = settingsSearch.retrieve_forthcoming;
};

const searchToSettings = (search: Search): any => {
  const settingsFileSearch = {
    ...settingsFile.search,
    retrieve_forthcoming: search.retrieveForthcoming,
  };
  return settingsFileSearch;
};

const prepFromSettings = (prep: Prep, settingsPrep: any) => {
  prep.fieldsToKeep = settingsPrep.fields_to_keep;

  for (const p of settingsPrep.prep_rounds) {
    const prepRound = new PrepRound();
    prepRound.name = p.name;
    prepRound.similarity = p.similarity;
    prepRound.scripts = scriptsFromSettings(p.scripts);
    prep.prepRounds.push(prepRound);
  }

  prep.manPrepScripts = scriptsFromSettings(settingsPrep.man_prep_scripts);
};

const prepToSettings = (prep: Prep): any => {
  const settingsFilePrep = {
    ...settingsFile.prep,
    fields_to_keep: prep.fieldsToKeep,
    prep_rounds: [],
    man_prep_scripts: scriptsToSettings(prep.manPrepScripts),
  };

  for (const p of prep.prepRounds) {
    const prep_round = {
      name: p.name,
      similarity: p.similarity,
      scripts: scriptsToSettings(p.scripts),
    };

    settingsFilePrep.prep_rounds.push(prep_round);
  }

  return settingsFilePrep;
};

const scriptsFromSettings = (settingsScripts: any) => {
  const scripts: Script[] = [];

  for (const settingsScript of settingsScripts) {
    const script = new Script();
    script.endpoint = settingsScript.endpoint;

    const paramsMap = new Map(Object.entries(settingsScript));
    paramsMap.delete("endpoint");
    script.parameters = paramsMap;

    scripts.push(script);
  }

  return scripts;
};

const scriptsToSettings = (scripts: Script[]) => {
  const settingsScripts: any[] = [];

  for (const script of scripts) {
    const paramsMap = new Map<string, any>();
    paramsMap.set("endpoint", script.endpoint);

    for (const [key, value] of Array.from(script.parameters)) {
      paramsMap.set(key, value);
    }

    const settingsScript = Object.fromEntries(paramsMap);

    settingsScripts.push(settingsScript);
  }

  return settingsScripts;
};

const dedupeFromSettings = (dedupe: Dedupe, settingsDedupe: any) => {
  dedupe.sameSourceMerges = settingsDedupe.same_source_merges;
  dedupe.scripts = scriptsFromSettings(settingsDedupe.scripts);
};

const dedupeToSettings = (dedupe: Dedupe): any => {
  const settingsDedupe = {
    same_source_merges: dedupe.sameSourceMerges,
    scripts: scriptsToSettings(dedupe.scripts),
  };

  return settingsDedupe;
};

const prescreenFromSettings = (
  prescreen: Prescreen,
  settingsPrescreen: any
) => {
  prescreen.explanation = settingsPrescreen.explanation;
  prescreen.scripts = scriptsFromSettings(settingsPrescreen.scripts);
};

const prescreenToSettings = (prescreen: Prescreen): any => {
  const settingsPrescreen = {
    explanation: prescreen.explanation,
    scripts: scriptsToSettings(prescreen.scripts),
  };

  return settingsPrescreen;
};

const pdfGetFromSettings = (pdfGet: PdfGet, settingsPdfGet: any) => {
  pdfGet.pdfPathType = settingsPdfGet.pdf_path_type;
  pdfGet.pdfRequiredForScreenAndSynthesis =
    settingsPdfGet.pdf_required_for_screen_and_synthesis;
  pdfGet.renamePdfs = settingsPdfGet.rename_pdfs;
  pdfGet.scripts = scriptsFromSettings(settingsPdfGet.scripts);
  pdfGet.manPdfGetScripts = scriptsFromSettings(
    settingsPdfGet.man_pdf_get_scripts
  );
};

const pdfGetToSettings = (pdfGet: PdfGet): any => {
  const settingsPdfGet = {
    pdf_path_type: pdfGet.pdfPathType,
    pdf_required_for_screen_and_synthesis:
      pdfGet.pdfRequiredForScreenAndSynthesis,
    rename_pdfs: pdfGet.renamePdfs,
    scripts: scriptsToSettings(pdfGet.scripts),
    man_pdf_get_scripts: scriptsToSettings(pdfGet.manPdfGetScripts),
  };

  return settingsPdfGet;
};

const pdfPrepFromSettings = (pdfPrep: PdfPrep, settingsPdfGet: any) => {
  pdfPrep.scripts = scriptsFromSettings(settingsPdfGet.scripts);
  pdfPrep.manPdfPrepScripts = scriptsFromSettings(
    settingsPdfGet.man_pdf_prep_scripts
  );
};

const pdfPrepToSettings = (pdfPrep: PdfPrep): any => {
  const settingsPdfPrep = {
    scripts: scriptsToSettings(pdfPrep.scripts),
    man_pdf_prep_scripts: scriptsToSettings(pdfPrep.manPdfPrepScripts),
  };

  return settingsPdfPrep;
};

const screenFromSettings = (screen: Screen, settingsScreen: any) => {
  screen.explanation = settingsScreen.explanation;
  screen.scripts = scriptsFromSettings(settingsScreen.scripts);
};

const screenToSettings = (screen: Screen): any => {
  const settingsScreen = {
    explanation: screen.explanation,
    criteria: {},
    scripts: scriptsToSettings(screen.scripts),
  };

  return settingsScreen;
};

const dataFromSettings = (data: Data, settingsData: any) => {
  data.scripts = scriptsFromSettings(settingsData.scripts);
};

const dataToSettings = (data: Data): any => {
  const settingsData = {
    scripts: scriptsToSettings(data.scripts),
  };

  return settingsData;
};

const getScriptDefinitions = async (
  packageType: string
): Promise<ScriptDefinition[]> => {
  const response = await httpService.get(
    `${apiEndpoint}/getScripts?packageType=${packageType}`
  );

  const scriptDefinitions: ScriptDefinition[] = [];

  for (const property in response.data) {
    const scriptDefinition = new ScriptDefinition();
    scriptDefinition.name = property;

    const propertyValues = response.data[property];
    scriptDefinition.description = propertyValues.description;
    scriptDefinition.endpoint = propertyValues.endpoint;

    scriptDefinitions.push(scriptDefinition);
  }

  return Promise.resolve<ScriptDefinition[]>(scriptDefinitions);
};

const getScriptParameterDefinitions = async (
  packageType: string,
  packageIdentifier: string
): Promise<ScriptParameterDefinition[]> => {
  const response = await httpService.get(
    `${apiEndpoint}/getScriptDetails?pakageType=${packageType}&packageIdentifier=${packageIdentifier}&endpointVersion=1.0`
  );

  const scriptParameterDefinitions: ScriptParameterDefinition[] = [];

  const paramsMap = new Map(Object.entries(response.data.parameters));

  for (const [key, value] of Array.from<any>(paramsMap)) {
    const param = new ScriptParameterDefinition();
    param.name = key;
    param.required = value.required;
    param.tooltip = value.tooltip;
    param.type = getScriptParameterType(value.type);
    param.min = value.min;
    param.max = value.max;

    scriptParameterDefinitions.push(param);
  }

  return Promise.resolve<ScriptParameterDefinition[]>(
    scriptParameterDefinitions
  );
};

const getScriptParameterType = (parameterType: string): ScriptParameterType => {
  let scriptParameterType = ScriptParameterType.String;

  switch (parameterType) {
    case "int":
      scriptParameterType = ScriptParameterType.Int;
      break;
    case "float":
      scriptParameterType = ScriptParameterType.Float;
      break;
    case "bool":
      scriptParameterType = ScriptParameterType.Boolean;
      break;
    case "str":
      scriptParameterType = ScriptParameterType.String;
      break;
    case "typing.Optional[dict]":
    case "typing.Optional[list]":
      scriptParameterType = ScriptParameterType.StringList;
      break;
  }

  return scriptParameterType;
};

const dataService = {
  getSettings,
  saveSettings,
  getScriptDefinitions,
  getScriptParameterDefinitions,
};

export default dataService;