"""
Celery worker CLI for running document processing tasks.
"""
import logging
import sys
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from .tasks import celery_app, get_task_status, get_queue_stats, purge_queue

console = Console()
app = typer.Typer(help="Celery Worker CLI for Ledger Lift")

@app.command()
def worker(
    concurrency: int = typer.Option(1, "--concurrency", "-c", help="Number of worker processes"),
    queues: str = typer.Option("document_processing", "--queues", "-q", help="Comma-separated list of queues"),
    loglevel: str = typer.Option("info", "--loglevel", "-l", help="Log level"),
    hostname: Optional[str] = typer.Option(None, "--hostname", help="Worker hostname"),
    without_gossip: bool = typer.Option(False, "--without-gossip", help="Disable gossip"),
    without_mingle: bool = typer.Option(False, "--without-mingle", help="Disable mingle"),
    without_heartbeat: bool = typer.Option(False, "--without-heartbeat", help="Disable heartbeat"),
):
    """Start a Celery worker."""
    console.print(Panel.fit(
        f"[bold blue]Starting Celery Worker[/bold blue]\n"
        f"Concurrency: {concurrency}\n"
        f"Queues: {queues}\n"
        f"Log Level: {loglevel}",
        title="Worker Configuration"
    ))
    
    try:
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, loglevel.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Start worker
        worker_args = [
            'worker',
            '--loglevel', loglevel,
            '--concurrency', str(concurrency),
            '--queues', queues,
        ]
        
        if hostname:
            worker_args.extend(['--hostname', hostname])
        if without_gossip:
            worker_args.append('--without-gossip')
        if without_mingle:
            worker_args.append('--without-mingle')
        if without_heartbeat:
            worker_args.append('--without-heartbeat')
        
        celery_app.worker_main(worker_args)
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Worker failed: {e}[/red]")
        sys.exit(1)

@app.command()
def status():
    """Show worker and queue status."""
    console.print(Panel.fit("[bold blue]Worker Status[/bold blue]", title="Status Check"))
    
    try:
        # Get queue stats
        stats = get_queue_stats()
        
        if 'error' in stats:
            console.print(f"[red]Error getting queue stats: {stats['error']}[/red]")
            return
        
        # Create status table
        table = Table(title="Queue Statistics")
        table.add_column("Queue", style="cyan")
        table.add_column("Active", style="green")
        table.add_column("Scheduled", style="yellow")
        table.add_column("Reserved", style="blue")
        
        for worker, tasks in stats.get('active_tasks', {}).items():
            table.add_row(
                worker,
                str(len(tasks)),
                str(len(stats.get('scheduled_tasks', {}).get(worker, []))),
                str(len(stats.get('reserved_tasks', {}).get(worker, [])))
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Failed to get status: {e}[/red]")

@app.command()
def task_status(task_id: str):
    """Get status of a specific task."""
    console.print(f"[blue]Getting status for task: {task_id}[/blue]")
    
    try:
        status = get_task_status(task_id)
        
        if status is None:
            console.print("[red]Task not found or error occurred[/red]")
            return
        
        # Create status panel
        status_text = f"""
[bold]Task ID:[/bold] {status['task_id']}
[bold]Status:[/bold] {status['status']}
[bold]Ready:[/bold] {status['ready']}
[bold]Successful:[/bold] {status['successful']}
[bold]Failed:[/bold] {status['failed']}
        """
        
        if status['result']:
            status_text += f"\n[bold]Result:[/bold] {status['result']}"
        
        console.print(Panel(status_text, title="Task Status"))
        
    except Exception as e:
        console.print(f"[red]Failed to get task status: {e}[/red]")

@app.command()
def purge(
    queue_name: str = typer.Option("document_processing", "--queue", "-q", help="Queue name to purge")
):
    """Purge all tasks from a queue."""
    console.print(f"[yellow]Purging queue: {queue_name}[/yellow]")
    
    try:
        success = purge_queue(queue_name)
        
        if success:
            console.print(f"[green]Successfully purged queue: {queue_name}[/green]")
        else:
            console.print(f"[red]Failed to purge queue: {queue_name}[/red]")
            
    except Exception as e:
        console.print(f"[red]Error purging queue: {e}[/red]")

@app.command()
def monitor():
    """Monitor worker activity in real-time."""
    console.print(Panel.fit("[bold blue]Worker Monitor[/bold blue]", title="Real-time Monitoring"))
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Monitoring workers...", total=None)
            
            while True:
                stats = get_queue_stats()
                
                if 'error' not in stats:
                    active_count = sum(len(tasks) for tasks in stats.get('active_tasks', {}).values())
                    scheduled_count = sum(len(tasks) for tasks in stats.get('scheduled_tasks', {}).values())
                    reserved_count = sum(len(tasks) for tasks in stats.get('reserved_tasks', {}).values())
                    
                    progress.update(
                        task,
                        description=f"Active: {active_count}, Scheduled: {scheduled_count}, Reserved: {reserved_count}"
                    )
                
                import time
                time.sleep(5)
                
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitoring stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Monitoring failed: {e}[/red]")

if __name__ == "__main__":
    app()