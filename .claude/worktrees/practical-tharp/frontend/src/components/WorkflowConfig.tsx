import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Button } from './ui/button';
import { X, Plus } from 'lucide-react';

interface WorkflowConfigProps {
  recipe: {
    type: 'workflow_enabled_content';
    base_recipe?: any;
    include_review?: boolean;
    include_translation?: boolean;
    include_approval?: boolean;
    reviewers?: string[];
    target_languages?: string[];
  };
  onChange: (recipe: any) => void;
}

export function WorkflowConfig({ recipe, onChange }: WorkflowConfigProps) {
  const addReviewer = () => {
    const reviewers = recipe.reviewers || [];
    onChange({ ...recipe, reviewers: [...reviewers, ''] });
  };

  const updateReviewer = (index: number, value: string) => {
    const reviewers = [...(recipe.reviewers || [])];
    reviewers[index] = value;
    onChange({ ...recipe, reviewers });
  };

  const removeReviewer = (index: number) => {
    const reviewers = [...(recipe.reviewers || [])];
    reviewers.splice(index, 1);
    onChange({ ...recipe, reviewers });
  };

  const addTargetLanguage = () => {
    const languages = recipe.target_languages || [];
    onChange({ ...recipe, target_languages: [...languages, ''] });
  };

  const updateTargetLanguage = (index: number, value: string) => {
    const languages = [...(recipe.target_languages || [])];
    languages[index] = value;
    onChange({ ...recipe, target_languages: languages });
  };

  const removeTargetLanguage = (index: number) => {
    const languages = [...(recipe.target_languages || [])];
    languages.splice(index, 1);
    onChange({ ...recipe, target_languages: languages });
  };

  const updateBaseRecipeType = (baseType: string) => {
    const baseRecipeDefaults: Record<string, any> = {
      task_topics: {
        type: 'task_topics',
        topic_count: 10,
        steps_per_task: 5,
        include_prereq: true,
        include_result: true,
        include_map: true,
        pretty_print: true,
      },
      concept_topics: {
        type: 'concept_topics',
        topic_count: 10,
        sections_per_concept: 3,
        include_map: true,
        pretty_print: true,
      },
      reference_topics: {
        type: 'reference_topics',
        topic_count: 10,
        properties_per_ref: 5,
        include_map: true,
        pretty_print: true,
      },
    };
    
    onChange({
      ...recipe,
      base_recipe: baseRecipeDefaults[baseType] || baseRecipeDefaults.task_topics,
    });
  };

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="base-recipe-type">Base Recipe Type</Label>
        <select
          id="base-recipe-type"
          className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-slate-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all"
          value={recipe.base_recipe?.type || 'task_topics'}
          onChange={(e) => updateBaseRecipeType(e.target.value)}
        >
          <option value="task_topics">Task Topics</option>
          <option value="concept_topics">Concept Topics</option>
          <option value="reference_topics">Reference Topics</option>
        </select>
        <p className="text-xs text-gray-600 mt-1">
          Select the base recipe type. Workflow metadata will be generated for all content created by this recipe.
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-review"
          checked={recipe.include_review !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, include_review: checked })}
        />
        <Label htmlFor="include-review">Include Review Workflow</Label>
      </div>

      {recipe.include_review !== false && (
        <div>
          <Label>Reviewers</Label>
          <div className="space-y-2">
            {(recipe.reviewers || ['reviewer1', 'reviewer2']).map((reviewer, index) => (
              <div key={index} className="flex gap-2">
                <Input
                  value={reviewer}
                  onChange={(e) => updateReviewer(index, e.target.value)}
                  placeholder="e.g., reviewer1"
                />
                <Button
                  onClick={() => removeReviewer(index)}
                  variant="ghost"
                  size="sm"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <Button onClick={addReviewer} variant="outline" size="sm">
              <Plus className="h-4 w-4 mr-2" />
              Add Reviewer
            </Button>
          </div>
        </div>
      )}

      <div className="flex items-center space-x-2">
        <Switch
          id="include-translation"
          checked={recipe.include_translation !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, include_translation: checked })}
        />
        <Label htmlFor="include-translation">Include Translation Workflow</Label>
      </div>

      {recipe.include_translation !== false && (
        <div>
          <Label>Target Languages</Label>
          <div className="space-y-2">
            {(recipe.target_languages || ['es', 'fr']).map((lang, index) => (
              <div key={index} className="flex gap-2">
                <Input
                  value={lang}
                  onChange={(e) => updateTargetLanguage(index, e.target.value)}
                  placeholder="e.g., es, fr, de"
                />
                <Button
                  onClick={() => removeTargetLanguage(index)}
                  variant="ghost"
                  size="sm"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <Button onClick={addTargetLanguage} variant="outline" size="sm">
              <Plus className="h-4 w-4 mr-2" />
              Add Language
            </Button>
          </div>
        </div>
      )}

      <div className="flex items-center space-x-2">
        <Switch
          id="include-approval"
          checked={recipe.include_approval !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, include_approval: checked })}
        />
        <Label htmlFor="include-approval">Include Approval Workflow</Label>
      </div>

      <div className="border rounded-lg p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
        <Label className="text-sm font-semibold mb-2 block">What You'll Get</Label>
        <div className="text-sm text-gray-700 space-y-1">
          <p>• <strong>Base Content:</strong> DITA topics and maps from the selected base recipe</p>
          <p>• <strong>Workflow Metadata:</strong> JSON file with review, translation, and approval workflow states</p>
          <p>• <strong>Review Data:</strong> Assignments, reviewers, comments, and approval status</p>
          <p>• <strong>Translation Jobs:</strong> Translation assignments for each target language</p>
          <p>• <strong>Approval Chains:</strong> Multi-level approval workflows with approvers</p>
          <p className="mt-2 text-xs text-gray-600">
            <strong>Note:</strong> This recipe generates workflow metadata files that can be used to test AEM Guides workflow features.
            Select a base recipe (like Task Topics or Concept Topics) to generate content, then workflow metadata will be added.
          </p>
        </div>
      </div>
    </div>
  );
}
