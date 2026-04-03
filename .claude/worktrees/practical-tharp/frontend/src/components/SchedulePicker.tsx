import { useState, useEffect } from 'react';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Clock, Calendar } from 'lucide-react';

interface SchedulePickerProps {
  onScheduleChange: (scheduledAt: Date | null, timezone: string) => void;
}

export function SchedulePicker({ onScheduleChange }: SchedulePickerProps) {
  const [enabled, setEnabled] = useState(false);
  const [dateTime, setDateTime] = useState('');
  const [timezone, setTimezone] = useState('UTC');

  useEffect(() => {
    if (!enabled) {
      onScheduleChange(null, timezone);
    } else if (dateTime) {
      const scheduledAt = new Date(dateTime);
      if (!isNaN(scheduledAt.getTime())) {
        onScheduleChange(scheduledAt, timezone);
      }
    }
  }, [enabled, dateTime, timezone, onScheduleChange]);

  const handleToggle = (checked: boolean) => {
    setEnabled(checked);
    if (!checked) {
      onScheduleChange(null, timezone);
    }
  };

  const updateSchedule = () => {
    if (dateTime) {
      const scheduledAt = new Date(dateTime);
      if (!isNaN(scheduledAt.getTime())) {
        onScheduleChange(scheduledAt, timezone);
      }
    }
  };

  const getMinDateTime = () => {
    const now = new Date();
    now.setMinutes(now.getMinutes() + 1);
    return now.toISOString().slice(0, 16);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between p-4 bg-slate-50/80 rounded-lg border border-slate-200 hover:border-slate-300 transition-colors">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-white rounded-md border border-slate-200">
            <Clock className="w-4 h-4 text-slate-600" />
          </div>
          <div>
            <Label htmlFor="schedule" className="text-sm font-semibold text-slate-900 cursor-pointer">
              Schedule for later
            </Label>
            <p className="text-xs text-slate-500 mt-0.5">Run job at a specific time</p>
          </div>
        </div>
        <Switch id="schedule" checked={enabled} onCheckedChange={handleToggle} />
      </div>
      
      {enabled && (
        <div className="space-y-4 p-5 bg-blue-50/30 rounded-lg border border-blue-200/50 animate-in slide-in-from-top-2 duration-200">
          <div className="space-y-2">
            <Label className="text-sm font-semibold text-slate-900 flex items-center gap-2">
              <Calendar className="w-4 h-4 text-slate-600" />
              Schedule Date & Time
            </Label>
            <Input
              type="datetime-local"
              value={dateTime}
              min={getMinDateTime()}
              onChange={(e) => {
                setDateTime(e.target.value);
                updateSchedule();
              }}
              className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-slate-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 hover:border-slate-400 transition-all"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-sm font-semibold text-slate-900">Timezone</Label>
            <select
              value={timezone}
              onChange={(e) => {
                setTimezone(e.target.value);
                updateSchedule();
              }}
              className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-slate-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 hover:border-slate-400 transition-all cursor-pointer"
            >
              <option value="UTC">UTC</option>
              <option value="America/New_York">Eastern Time</option>
              <option value="America/Chicago">Central Time</option>
              <option value="America/Denver">Mountain Time</option>
              <option value="America/Los_Angeles">Pacific Time</option>
              <option value="Europe/London">London</option>
              <option value="Asia/Kolkata">India</option>
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
