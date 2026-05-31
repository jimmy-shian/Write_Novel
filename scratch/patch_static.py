import os

# --- PATCH static/pipeline.js ---
pipeline_path = "static/pipeline.js"
pipeline_old = "static/pipeline.js.old"

with open(pipeline_path, "r", encoding="utf-8") as f:
    pipeline_content = f.read()

old_pipeline_plot = """            case 'plot':
                endpoint = '/api/agent/plot-planner';
                body = { novel_id: state.currentNovelId, user_prompt: userPrompt };
                targetTextarea = el.editorPlotJson;"""

new_pipeline_plot = """            case 'plot':
                endpoint = '/api/agent/plot-planner';
                body = { 
                    novel_id: state.currentNovelId, 
                    chapter_index: state.activeChapterIndex || 1,
                    user_prompt: userPrompt 
                };
                targetTextarea = el.editorPlotJson;"""

pipeline_content = pipeline_content.replace(old_pipeline_plot, new_pipeline_plot)

# Rename bypass for pipeline.js
if os.path.exists(pipeline_old):
    os.remove(pipeline_old)
os.rename(pipeline_path, pipeline_old)

with open(pipeline_path, "w", encoding="utf-8") as f:
    f.write(pipeline_content)

os.remove(pipeline_old)
print("pipeline.js patched successfully!")


# --- PATCH static/app.js ---
app_path = "static/app.js"
app_old = "static/app.js.old"

with open(app_path, "r", encoding="utf-8") as f:
    app_content = f.read()

# 1. Modify runDirectorDecision call in app.js
old_director_decision = """        streamAPI(
            '/api/novels/' + state.currentNovelId + '/director-decision',
            { current_stage: currentStage, user_prompt: userPrompt },"""

new_director_decision = """        streamAPI(
            '/api/novels/' + state.currentNovelId + '/director-decision',
            { 
                current_stage: currentStage, 
                user_prompt: userPrompt,
                chapter_index: state.activeChapterIndex || 1
            },"""

app_content = app_content.replace(old_director_decision, new_director_decision)

# 2. Modify plot-planner call at line 3006
old_app_plot_3006 = """        case 'plot-planner':
            showToast("📋 執行劇情規劃師（全量生成）...");
            showAgentProcessingIndicator('plot', 'Plot Planner (全量生成)');
            return new Promise((resolve) => {
                el.editorPlotJson.value = '';
                streamAPI(
                    '/api/agent/plot-planner',
                    { novel_id: state.currentNovelId, user_prompt: user_prompt || params.hint },"""

new_app_plot_3006 = """        case 'plot-planner':
            showToast("📋 執行劇情規劃師（全量生成）...");
            showAgentProcessingIndicator('plot', 'Plot Planner (全量生成)');
            return new Promise((resolve) => {
                el.editorPlotJson.value = '';
                streamAPI(
                    '/api/agent/plot-planner',
                    { 
                        novel_id: state.currentNovelId, 
                        chapter_index: params.chapter_index || state.activeChapterIndex || 1,
                        user_prompt: user_prompt || params.hint 
                    },"""

app_content = app_content.replace(old_app_plot_3006, new_app_plot_3006)

# 3. Modify plot-planner call at line 3194
old_app_plot_3194 = """        case 'plot':
        case '章節大綱':
            showToast("🔄 重新生成章節大綱...");
            showAgentProcessingIndicator('plot', 'Plot Planner (重新生成)');
            return new Promise((resolve) => {
                el.editorPlotJson.value = '';
                const prompt = hint || "請重新規劃章節大綱";
                streamAPI(
                    '/api/agent/plot-planner',
                    { novel_id: state.currentNovelId, user_prompt: prompt },"""

new_app_plot_3194 = """        case 'plot':
        case '章節大綱':
            showToast("🔄 重新生成章節大綱...");
            showAgentProcessingIndicator('plot', 'Plot Planner (重新生成)');
            return new Promise((resolve) => {
                el.editorPlotJson.value = '';
                const prompt = hint || "請重新規劃章節大綱";
                streamAPI(
                    '/api/agent/plot-planner',
                    { 
                        novel_id: state.currentNovelId, 
                        chapter_index: state.activeChapterIndex || 1,
                        user_prompt: prompt 
                    },"""

app_content = app_content.replace(old_app_plot_3194, new_app_plot_3194)

# 4. Modify plot-planner call at line 4102
old_app_plot_4102 = """    // STAGE 3: 章節大綱
    function startStage3_Plot() {
        addGlowEffect(plotTab, true);
        state.activeTab = 'plot';
        renderActiveTab();
        if (el.editorPlotJson) el.editorPlotJson.value = '';
        showToast("總監批准！正在啟動大綱規劃師 Agent...");
        
        streamAPI(
            '/api/agent/plot-planner',
            { novel_id: state.currentNovelId, user_prompt: userPrompt },"""

new_app_plot_4102 = """    // STAGE 3: 章節大綱
    function startStage3_Plot() {
        addGlowEffect(plotTab, true);
        state.activeTab = 'plot';
        renderActiveTab();
        if (el.editorPlotJson) el.editorPlotJson.value = '';
        showToast("總監批准！正在啟動大綱規劃師 Agent...");
        
        streamAPI(
            '/api/agent/plot-planner',
            { 
                novel_id: state.currentNovelId, 
                chapter_index: state.activeChapterIndex || 1,
                user_prompt: userPrompt 
            },"""

app_content = app_content.replace(old_app_plot_4102, new_app_plot_4102)

# 5. Modify plot-planner call at line 4294
old_app_plot_4294 = """    if (state.activeDrawerAction === 'plot') {
        startAgentStream(
            '/api/agent/plot-planner',
            { novel_id: state.currentNovelId, user_prompt: userPrompt },"""

new_app_plot_4294 = """    if (state.activeDrawerAction === 'plot') {
        startAgentStream(
            '/api/agent/plot-planner',
            { 
                novel_id: state.currentNovelId, 
                chapter_index: state.activeChapterIndex || 1,
                user_prompt: userPrompt 
            },"""

app_content = app_content.replace(old_app_plot_4294, new_app_plot_4294)

# 6. Modify plot-planner call at line 5348
old_app_plot_5348 = """    streamAPI(
        '/api/agent/plot-planner',
        { novel_id: state.currentNovelId, user_prompt: plotPrompt },"""

new_app_plot_5348 = """    streamAPI(
        '/api/agent/plot-planner',
        { 
            novel_id: state.currentNovelId, 
            chapter_index: state.activeChapterIndex || 1,
            user_prompt: plotPrompt 
        },"""

app_content = app_content.replace(old_app_plot_5348, new_app_plot_5348)

# Rename bypass for app.js
if os.path.exists(app_old):
    os.remove(app_old)
os.rename(app_path, app_old)

with open(app_path, "w", encoding="utf-8") as f:
    f.write(app_content)

os.remove(app_old)
print("app.js patched successfully!")
