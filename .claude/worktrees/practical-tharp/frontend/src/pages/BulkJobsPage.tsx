import { useState } from 'react';
import { BulkJobCreator } from '@/components/BulkJobCreator';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

/**
 * Bulk Jobs Page
 * 
 * This page allows users to:
 * - Create multiple jobs at once
 * - Import jobs from CSV
 * - Create jobs from templates with variations
 */
export function BulkJobsPage() {
  const [createdJobIds, setCreatedJobIds] = useState<string[]>([]);
  // const navigate = useNavigate(); // Uncomment if using React Router

  const handleJobsCreated = (jobIds: string[]) => {
    setCreatedJobIds(jobIds);
    
    // Optionally navigate to jobs page
    // navigate('/jobs');
    
    // Or show success message
    console.log(`Created ${jobIds.length} jobs:`, jobIds);
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Bulk Job Creator</CardTitle>
        </CardHeader>
        <CardContent>
          <BulkJobCreator onJobsCreated={handleJobsCreated} />
        </CardContent>
      </Card>

      {createdJobIds.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Created Jobs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <p className="text-sm text-gray-600">
                Successfully created {createdJobIds.length} job(s)
              </p>
              <div className="flex flex-wrap gap-2">
                {createdJobIds.map(jobId => (
                  <Button
                    key={jobId}
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      // Navigate to job details
                      // navigate(`/jobs/${jobId}`);
                      console.log('View job:', jobId);
                    }}
                  >
                    View Job {jobId.slice(0, 8)}
                  </Button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default BulkJobsPage;
