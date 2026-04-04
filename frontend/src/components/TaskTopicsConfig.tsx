import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface TaskTopicsConfigProps {
  recipe: {
    topic_count?: number;
    steps_per_task?: number;
    include_prereq?: boolean;
    include_result?: boolean;
    include_choicetable?: boolean;
    include_map?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function TaskTopicsConfig({ recipe, onChange }: TaskTopicsConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>Topic Count</Label>
        <Input
          type="number"
          value={recipe.topic_count || 50}
          onChange={(e) => onChange({
            type: 'task_topics',
            topic_count: parseInt(e.target.value) || 50,
            steps_per_task: recipe.steps_per_task ?? 5,
            include_prereq: recipe.include_prereq ?? true,
            include_result: recipe.include_result ?? true,
            include_map: recipe.include_map ?? true,
            pretty_print: recipe.pretty_print ?? true,
          })}
          min={10}
          max={5000}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of Task topics to generate
        </p>
      </div>

      <div>
        <Label>Steps per Task</Label>
        <Input
          type="number"
          value={recipe.steps_per_task || 5}
          onChange={(e) => onChange({
            type: 'task_topics',
            topic_count: recipe.topic_count ?? 50,
            steps_per_task: parseInt(e.target.value) || 5,
            include_prereq: recipe.include_prereq ?? true,
            include_result: recipe.include_result ?? true,
            include_map: recipe.include_map ?? true,
            pretty_print: recipe.pretty_print ?? true,
          })}
          min={1}
          max={20}
        />
        <p className="text-sm text-gray-500 mt-1">
          Average number of steps in each task
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-prereq"
          checked={recipe.include_prereq !== false}
          onCheckedChange={(checked) => onChange({
            type: 'task_topics',
            topic_count: recipe.topic_count ?? 50,
            steps_per_task: recipe.steps_per_task ?? 5,
            include_prereq: checked,
            include_result: recipe.include_result ?? true,
            include_map: recipe.include_map ?? true,
            pretty_print: recipe.pretty_print ?? true,
          })}
        />
        <Label htmlFor="include-prereq">Include Prerequisites</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-result"
          checked={recipe.include_result !== false}
          onCheckedChange={(checked) => onChange({
            type: 'task_topics',
            topic_count: recipe.topic_count ?? 50,
            steps_per_task: recipe.steps_per_task ?? 5,
            include_prereq: recipe.include_prereq ?? true,
            include_result: checked,
            include_map: recipe.include_map ?? true,
            pretty_print: recipe.pretty_print ?? true,
          })}
        />
        <Label htmlFor="include-result">Include Results</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-choicetable"
          checked={recipe.include_choicetable === true}
          onCheckedChange={(checked) => onChange({
            ...recipe,
            type: 'task_topics',
            include_choicetable: checked,
          })}
        />
        <Label htmlFor="include-choicetable">Include Choicetable</Label>
        <p className="text-xs text-gray-400 ml-1">(adds choicetable to every topic; ~20% get one by default)</p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-map"
          checked={recipe.include_map !== false}
          onCheckedChange={(checked) => onChange({
            type: 'task_topics',
            topic_count: recipe.topic_count ?? 50,
            steps_per_task: recipe.steps_per_task ?? 5,
            include_prereq: recipe.include_prereq ?? true,
            include_result: recipe.include_result ?? true,
            include_choicetable: recipe.include_choicetable ?? false,
            include_map: checked,
            pretty_print: recipe.pretty_print ?? true,
          })}
        />
        <Label htmlFor="include-map">Include Map</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="pretty-print"
          checked={recipe.pretty_print !== false}
          onCheckedChange={(checked) => onChange({
            type: 'task_topics',
            topic_count: recipe.topic_count ?? 50,
            steps_per_task: recipe.steps_per_task ?? 5,
            include_prereq: recipe.include_prereq ?? true,
            include_result: recipe.include_result ?? true,
            include_map: recipe.include_map ?? true,
            pretty_print: checked,
          })}
        />
        <Label htmlFor="pretty-print">Pretty Print XML</Label>
      </div>
    </div>
  );
}
